import os
import shutil
import subprocess
import sys
from Rom import Rom
from N64Patch import apply_patch_file

if len(sys.argv) < 2:
    print('Usage: py patcher.exe base_rom patch_file [output_file]')
    exit()

patched_file = 'patched.z64'

# If the user specified an output file, use that filename
if len(sys.argv) > 3:
    output_file = os.path.basename(sys.argv[3])
else:
    output_file = 'output.z64'

# Decompress the base OoT file if necessary
rom = Rom(sys.argv[1])

# Apply the patch to the decompressed file
apply_patch_file(rom, sys.argv[2])

# Write the patched ROM to disk
rom.write_to_file(patched_file)

# Compress the patched ROM
subprocess.call(['Compress.exe', patched_file, output_file])

# Move the ROM file to the requested directory, if present
if len(sys.argv) > 3:
    shutil.move(output_file, sys.argv[3])

# Delete the working files
os.remove('ARCHIVE.bin')
os.remove('ZOOTDEC.z64')
os.remove(patched_file)
