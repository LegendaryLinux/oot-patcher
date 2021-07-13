from distutils.core import setup
import py2exe

setup(
    console=['Patch.py'],
    name="OoT Patcher",
    data_files=[('', ['dmaTable.dat', 'symbols.json', 'Compress.exe', 'Decompress.exe'])],

    options={'py2exe': {
        'optimize': 2,
        'bundle_files': 2,
    }}
    )
