from btypes import *

bool8 = BasicType('?',BIG_ENDIAN)
sint8 = BasicType('b',BIG_ENDIAN)
uint8 = BasicType('B',BIG_ENDIAN)
sint16 = BasicType('h',BIG_ENDIAN)
uint16 = BasicType('H',BIG_ENDIAN)
sint32 = BasicType('l',BIG_ENDIAN)
uint32 = BasicType('L',BIG_ENDIAN)
sint64 = BasicType('q',BIG_ENDIAN)
uint64 = BasicType('Q',BIG_ENDIAN)
float32 = BasicType('f',BIG_ENDIAN)
float64 = BasicType('d',BIG_ENDIAN)
cstring = CString('ascii')
pstring = PString(uint8,'ascii')

