import struct as _struct


class BasicType:

    def __init__(self,format_character,endianess):
        self.format_character = format_character
        self.endianess = endianess
        self.format_string = endianess + format_character
        self.size = _struct.calcsize(self.format_string)

    def pack(self,stream,value):
        stream.write(_struct.pack(self.format_string,value))

    def unpack(self,stream):
        return _struct.unpack(self.format_string,stream.read(self.size))[0]

    def sizeof(self):
        return self.size


class FixedPointConverter:

    def __init__(self,integer_type,scale):
        self.integer_type = integer_type
        self.scale = scale

    def pack(self,stream,value):
        self.integer_type.pack(stream,int(value/self.scale))

    def unpack(self,stream):
        return self.integer_type.unpack(stream)*self.scale

    def sizeof(self):
        return self.integer_type.sizeof()


class ByteString:

    def __init__(self,length):
        self.length = length

    def pack(self,stream,string):
        if len(string) != self.length:
            raise ValueError('wrong string length')
        stream.write(string)

    def unpack(self,stream):
        return stream.read(self.length)

    def sizeof(self):
        return self.length


class Array:

    def __init__(self,element_type,length):
        self.element_type = element_type
        self.length = length

    def pack(self,stream,array):
        if len(array) != self.length:
            raise ValueError('wrong array length')
        for value in array:
            self.element_type.pack(stream,value)

    def unpack(self,stream):
        return [self.element_type.unpack(stream) for i in range(self.length)]

    def sizeof(self):
        return self.length*self.element_type.sizeof()


class CString:

    def __init__(self,encoding):
        self.encoding = encoding

    def pack(self,stream,string):
        stream.write((string + '\0').encode(self.encoding))

    def unpack(self,stream):
        #XXX: This might not work for all encodings
        null = '\0'.encode(self.encoding)
        string = b''
        while True:
            c = stream.read(len(null))
            if c == null: break
            string += c
        return string.decode(self.encoding)

    def sizeof(self):
        return None


class PString:

    def __init__(self,length_type,encoding):
        self.length_type = length_type
        self.encoding = encoding

    def pack(self,stream,string):
        string = string.encode(self.encoding)
        self.length_type.pack(stream,len(string))
        stream.write(string)

    def unpack(self,stream):
        length = self.length_type.unpack(stream)
        return stream.read(length).decode(self.encoding)

    def sizeof(self):
        return None


class Field:

    def __init__(self,name,field_type):
        self.name = name
        self.field_type = field_type

    def pack(self,stream,struct):
        self.field_type.pack(stream,getattr(struct,self.name))

    def unpack(self,stream,struct):
        setattr(struct,self.name,self.field_type.unpack(stream))

    def sizeof(self):
        return self.field_type.sizeof()

    def equal(self,struct,other):
        return getattr(struct,self.name) == getattr(other,self.name)


class Padding:

    def __init__(self,length,padding=b'\xFF'):
        self.length = length
        self.padding = padding

    def pack(self,stream,struct):
        stream.write(self.padding*self.length)

    def unpack(self,stream,struct):
        stream.read(self.length)

    def sizeof(self):
        return self.length

    def equal(self,struct,other):
        return True


class StructClassDictionary(dict):

    def __init__(self):
        super().__init__()
        self.struct_fields = []

    def __setitem__(self,key,value):
        if not key[:2] == key[-2:] == '__' and not hasattr(value,'__get__'):
            self.struct_fields.append(Field(key,value))
        elif key == '__padding__':
            self.struct_fields.append(value)
        else:
            super().__setitem__(key,value)


class StructMetaClass(type):

    @classmethod
    def __prepare__(metacls,cls,bases):
        return StructClassDictionary()

    def __new__(metacls,cls,bases,classdict):
        if any(field.sizeof() is None for field in classdict.struct_fields):
            struct_size = None
        else:
            struct_size = sum(field.sizeof() for field in classdict.struct_fields)

        struct_class = type.__new__(metacls,cls,bases,classdict)
        struct_class.struct_fields = classdict.struct_fields
        struct_class.struct_size = struct_size
        return struct_class

    def __init__(self,cls,bases,classdict):
        super().__init__(cls,bases,classdict)


class Struct(metaclass=StructMetaClass):

    __slots__ = tuple()

    def __eq__(self,other):
        return all(field.equal(self,other) for field in self.struct_fields)

    @classmethod
    def pack(cls,stream,struct):
        for field in cls.struct_fields:
            field.pack(stream,struct)

    @classmethod
    def unpack(cls,stream):
        struct = cls.__new__(cls) #TODO: what if __init__ does something important?
        for field in cls.struct_fields:
            field.unpack(stream,struct)
        return struct

    @classmethod
    def sizeof(cls):
        return cls.struct_size

