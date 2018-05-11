bl_info = {
    "name": "Export COL for Super Mario Sunshine",
    "author": "Blank",
    "version": (1, 0, 0),
    "blender": (2, 71, 0),
    "location": "File > Export > Collision (.col)",
    "description": "This script allows you do export col files directly from blender. Based on Blank's obj2col",
    "warning": "Might break, doing this mostly for my own convinience",
    "category": "Import-Export"
}

import bpy
import bmesh
from btypes.big_endian import *
import os
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
    FloatProperty,
    StringProperty,
    EnumProperty,
    )


class Header(Struct):
    vertex_count = uint32
    vertex_offset = uint32
    group_count = uint32
    group_offset = uint32


class Vertex(Struct):
    x = float32
    y = float32
    z = float32

    def __init__(self,x,y,z):
        self.x = x
        self.y = y
        self.z = z


class Group(Struct):
    unknown0 = uint8 # 0,1,2,4,6,7,8,64,128,129,132,135,160,192, bitfield?
    unknown1 = uint8 # 0-12
    triangle_count = uint16
    __padding__ = Padding(1,b'\x00')
    has_unknown4 = bool8
    __padding__ = Padding(2)
    vertex_index_offset = uint32
    unknown2_offset = uint32 # 0-18,20,21,23,24,27-31
    unknown3_offset = uint32 # 0-27
    unknown4_offset = uint32 # 0,1,2,3,4,8,255,6000,7500,7800,8000,8400,9000,10000,10300,12000,14000,17000,19000,20000,21000,22000,27500,30300


class Triangle:

    def __init__(self):
        self.vertex_indices = None
        self.unknown0 = 128
        self.unknown1 = 0
        self.unknown2 = 0
        self.unknown3 = 0
        self.unknown4 = None

    @property
    def has_unknown4(self):
        return self.unknown4 is not None


def pack(stream,vertices,triangles): #pack triangles into col file
    groups = []

    for triangle in triangles:
        for group in groups: #for each triangle add to appropriate group
            if triangle.unknown0 != group.unknown0: continue #break out of loop to next cycle
            if triangle.unknown1 != group.unknown1: continue 
            if triangle.has_unknown4 != group.has_unknown4: continue
            group.triangles.append(triangle)
            break
        else: #if no group has been found
            group = Group() #create a new group
            group.unknown0 = triangle.unknown0
            group.unknown1 = triangle.unknown1
            group.has_unknown4 = triangle.has_unknown4
            group.triangles = [triangle]
            groups.append(group) #add to list of groups

    header = Header()
    header.vertex_count = len(vertices)
    header.vertex_offset = Header.sizeof() + Group.sizeof()*len(groups)
    header.group_count = len(groups)
    header.group_offset = Header.sizeof()
    Header.pack(stream,header) 

    stream.write(b'\x00'*Group.sizeof()*len(groups))

    for vertex in vertices:
        Vertex.pack(stream,vertex)

    for group in groups:
        group.triangle_count = len(group.triangles)
        group.vertex_index_offset = stream.tell()
        for triangle in group.triangles:
            uint16.pack(stream,triangle.vertex_indices[0])
            uint16.pack(stream,triangle.vertex_indices[1])
            uint16.pack(stream,triangle.vertex_indices[2])

    for group in groups:
        group.unknown2_offset = stream.tell()
        for triangle in group.triangles:
            uint8.pack(stream,triangle.unknown2)

    for group in groups:
        group.unknown3_offset = stream.tell()
        for triangle in group.triangles:
            uint8.pack(stream,triangle.unknown3)

    for group in groups:
        if not group.has_unknown4:
            group.unknown4_offset = 0
        else:
            group.unknown4_offset = stream.tell()
            for triangle in group.triangles:
                uint16.pack(stream,triangle.unknown4)

    stream.seek(header.group_offset)
    for group in groups:
        Group.pack(stream,group)
        

def unpack(stream):
    header = Header.unpack(stream)

    stream.seek(header.group_offset)
    groups = [Group.unpack(stream) for _ in range(header.group_count)]

    stream.seek(header.vertex_offset)
    vertices = [Vertex.unpack(stream) for _ in range(header.vertex_count)]

    for group in groups:
        group.triangles = [Triangle() for _ in range(group.triangle_count)]
        for triangle in group.triangles:
            triangle.unknown0 = group.unknown0
            triangle.unknown1 = group.unknown1

    for group in groups:
        stream.seek(group.vertex_index_offset)
        for triangle in group.triangles:
            triangle.vertex_indices = [uint16.unpack(stream) for _ in range(3)]

    for group in groups:
        stream.seek(group.unknown2_offset)
        for triangle in group.triangles:
            triangle.unknown2 = uint8.unpack(stream)

    for group in groups:
        stream.seek(group.unknown3_offset)
        for triangle in group.triangles:
            triangle.unknown3 = uint8.unpack(stream)

    for group in groups:
        if not group.has_unknown4: continue
        stream.seek(group.unknown4_offset)
        for triangle in group.triangles:
            triangle.unknown4 = uint16.unpack(stream)

    triangles = sum((group.triangles for group in groups),[])

    return vertices,triangles

class ExportCOL(bpy.types.Operator, ExportHelper):
    """Save a COL file"""
    bl_idname = "export_mesh.col"
    bl_label = "Export COL"
    filter_glob = StringProperty(
        default="*.col",
        options={'HIDDEN'},
    )

    check_extension = True
    filename_ext = ".col"
	
	#To do: add material presets
	
    def execute(self, context):        # execute() is called by blender when running the operator.
        VertexList = []
        Triangles = []
        bm = bmesh.new()
        for Obj in bpy.context.scene.objects: #join all objects
            MyMesh = Obj.to_mesh(context.scene, True, 'PREVIEW')#make a copy of the object we can modify freely
            bm.from_mesh(MyMesh)
        
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=0, ngon_method=0) #triangulate bmesh
        #triangulate_mesh(Mesh)
        Mesh = bpy.data.meshes.new( "newMesh" )
        bm.to_mesh(Mesh)
        
        for Vert in Mesh.vertices:
            VertexList.append(Vertex(Vert.co.x,Vert.co.z,-Vert.co.y)) #add in verts, make sure y is up

        for Face in Mesh.polygons:
            MyTriangle = Triangle()
            MyTriangle.vertex_indices = [Face.vertices[0],Face.vertices[1],Face.vertices[2]] #add three vertex indicies
            Triangles.append(MyTriangle) #add triangles
        
        ColStream = open(self.filepath,'wb')
        pack(ColStream,VertexList,Triangles)
        bpy.data.meshes.remove(Mesh) #delete mesh
        return {'FINISHED'}            # this lets blender know the operator finished successfully.

class CollisionPanel(bpy.types.Panel):
    bl_label = "Hello from Object context"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
 
    def draw(self, context):
        self.layout.operator("hello.hello", text='Bonjour').country = "France"
    
def register():
    bpy.utils.register_class(ExportCOL)
    bpy.types.INFO_MT_file_export.append(menu_func)

def menu_func(self, context):
    self.layout.operator(ExportCOL.bl_idname, text="Collision (.col)")
    
def unregister():
    bpy.utils.unregister_class(ExportCOL)
    bpy.types.INFO_MT_file_export.remove(menu_func)


# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()