"""Small ARM64 PE/FDT layout fixture for packaging tests. Never a bootable kernel."""
import struct


def image_with_dtb():
    strings = b'compatible\0'
    compatible = b'microsoft,romulus13\0'
    structure = (struct.pack('>I', 1) + b'\0' * 4 + struct.pack('>III', 3, len(compatible), 0)
                 + compatible + bytes(-len(compatible) % 4) + struct.pack('>II', 2, 9))
    header = struct.pack('>10I', 0xd00dfeed, 56 + len(structure) + len(strings),
                         56, 56 + len(structure), 40, 17, 16, 0, len(strings), len(structure))
    dtb = header + b'\0' * 16 + structure + strings
    raw_size = (len(dtb) + 511) // 512 * 512
    image = bytearray(512 + raw_size)
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 0x3c, 64)
    image[64:68] = b'PE\0\0'
    struct.pack_into('<HH', image, 68, 0xaa64, 1)
    struct.pack_into('<H', image, 84, 0)
    image[88:96] = b'.dtbauto'
    struct.pack_into('<IIII', image, 96, len(dtb), 0x1000, raw_size, 512)
    image[512:512 + len(dtb)] = dtb
    return bytes(image), dtb
