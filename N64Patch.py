import zlib
import zipfile
from ntype import BigStream


# get the next XOR key. Uses some location in the source rom.
# This will skip of 0s, since if we hit a block of 0s, the
# patch data will be raw.
def key_next(rom, key_address, address_range):
    key = 0
    while key == 0:
        key_address += 1
        if key_address > address_range[1]:
            key_address = address_range[0]
        key = rom.original.buffer[key_address]
    return key, key_address


# creates a XOR block for the patch. This might break it up into
# multiple smaller blocks if there is a concern about the XOR key
# or if it is too long.
def write_block(rom, xor_address, xor_range, block_start, data, patch_data):
    new_data = []
    key_offset = 0
    continue_block = False

    for b in data:
        if b == 0:
            # Leave 0s as 0s. Do not XOR
            new_data += [0]
        else:
            # get the next XOR key
            key, xor_address = key_next(rom, xor_address, xor_range)

            # if the XOR would result in 0, change the key.
            # This requires breaking up the block.
            if b == key:
                write_block_section(block_start, key_offset, new_data, patch_data, continue_block)
                new_data = []
                key_offset = 0
                continue_block = True

                # search for next safe XOR key
                while b == key:
                    key_offset += 1
                    key, xor_address = key_next(rom, xor_address, xor_range)
                    # if we aren't able to find one quickly, we may need to break again
                    if key_offset == 0xFF:
                        write_block_section(block_start, key_offset, new_data, patch_data, continue_block)
                        new_data = []
                        key_offset = 0
                        continue_block = True

            # XOR the key with the byte
            new_data += [b ^ key]

            # Break the block if it's too long
            if (len(new_data) == 0xFFFF):
                write_block_section(block_start, key_offset, new_data, patch_data, continue_block)
                new_data = []
                key_offset = 0
                continue_block = True

    # Save the block
    write_block_section(block_start, key_offset, new_data, patch_data, continue_block)
    return xor_address


# This saves a sub-block for the XOR block. If it's the first part
# then it will include the address to write to. Otherwise it will
# have a number of XOR keys to skip and then continue writing after
# the previous block
def write_block_section(start, key_skip, in_data, patch_data, is_continue):
    if not is_continue:
        patch_data.append_int32(start)
    else:
        patch_data.append_bytes([0xFF, key_skip])
    patch_data.append_int16(len(in_data))
    patch_data.append_bytes(in_data)


# This will apply a patch file to a source rom to generate a patched rom.
def apply_patch_file(rom, file, sub_file=None):
    # load the patch file and decompress
    if sub_file:
        with zipfile.ZipFile(file, 'r') as patch_archive:
            try:
                with patch_archive.open(sub_file, 'r') as stream:
                    patch_data = stream.read()
            except KeyError as ex:
                raise FileNotFoundError('Patch file missing from archive. Invalid Player ID.')
    else:
        with open(file, 'rb') as stream:
            patch_data = stream.read()
    patch_data = BigStream(zlib.decompress(patch_data))

    # make sure the header is correct
    if patch_data.read_bytes(length=4) != b'ZPFv':
        raise Exception("File is not in a Zelda Patch Format")
    if patch_data.read_byte() != ord('1'):
        # in the future we might want to have revisions for this format
        raise Exception("Unsupported patch version.")

    # load the patch configuration info. The fact that the DMA Table is
    # included in the patch is so that this might be able to work with
    # other N64 games.
    dma_start = patch_data.read_int32()
    xor_range = (patch_data.read_int32(), patch_data.read_int32())
    xor_address = patch_data.read_int32()

    # Load all the DMA table updates. This will move the files around.
    # A key thing is that some of these entries will list a source file
    # that they are from, so we know where to copy from, no matter where
    # in the DMA table this file has been moved to. Also important if a file
    # is copied. This list is terminated with 0xFFFF
    while True:
        # Load DMA update
        dma_index = patch_data.read_int16()
        if dma_index == 0xFFFF:
            break

        from_file = patch_data.read_int32()
        start = patch_data.read_int32()
        size = patch_data.read_int24()

        # Save new DMA Table entry
        dma_entry = dma_start + (dma_index * 0x10)
        end = start + size
        rom.write_int32(dma_entry, start)
        rom.write_int32(None,      end)
        rom.write_int32(None,      start)
        rom.write_int32(None,      0)

        if from_file != 0xFFFFFFFF:
            # If a source file is listed, copy from there
            old_dma_start, old_dma_end, old_size = rom.original.get_dmadata_record_by_key(from_file)
            copy_size = min(size, old_size)
            rom.write_bytes(start, rom.original.read_bytes(from_file, copy_size))
            rom.buffer[start+copy_size:start+size] = [0] * (size - copy_size)
        else:
            # if it's a new file, fill with 0s
            rom.buffer[start:start+size] = [0] * size

    # Read in the XOR data blocks. This goes to the end of the file.
    block_start = None
    while not patch_data.eof():
        is_new_block = patch_data.read_byte() != 0xFF

        if is_new_block:
            # start writing a new block
            patch_data.seek_address(delta=-1)
            block_start = patch_data.read_int32()
            block_size = patch_data.read_int16()
        else:
            # continue writing from previous block
            key_skip = patch_data.read_byte()
            block_size = patch_data.read_int16()
            # skip specified XOR keys
            for _ in range(key_skip):
                key, xor_address = key_next(rom, xor_address, xor_range)

        # read in the new data
        data = []
        for b in patch_data.read_bytes(length=block_size):
            if b == 0:
                # keep 0s as 0s
                data += [0]
            else:
                # The XOR will always be safe and will never produce 0
                key, xor_address = key_next(rom, xor_address, xor_range)
                data += [b ^ key]

        # Save the new data to rom
        rom.write_bytes(block_start, data)
        block_start = block_start+block_size

