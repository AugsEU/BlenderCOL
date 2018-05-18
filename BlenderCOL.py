bl_info = {
    "name": "Export COL for Super Mario Sunshine",
    "author": "Blank",
    "version": (1, 0, 0),
    "blender": (2, 71, 0),
    "location": "File > Export > Collision (.col)",
    "description": "This script allows you do export col files directly from blender. Based on Blank's obj2col",
    "warning": "Runs update function every 0.2 seconds",
    "category": "Import-Export"
}
import math
import bpy
import bmesh
import threading
from enum import Enum
from btypes.big_endian import *
from bpy.types import PropertyGroup, Panel, Scene, Operator
from bpy.utils import register_class, unregister_class
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
    FloatProperty,
    StringProperty,
    EnumProperty, 
    IntProperty,
    PointerProperty,
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

class ImportCOL(Operator, ExportHelper): #Operator that exports the collision model into .col file
    """Import a COL file"""
    bl_idname = "import_mesh.col"
    bl_label = "Import COL"
    filter_glob = StringProperty( 
        default="*.col",
        options={'HIDDEN'},
    )#This property filters what you see in the file browser to just .col files

    check_extension = True
    filename_ext = ".col" #This is the extension that the model will have
    def execute(self, context):
        ColStream = open(self.filepath,'rb')
        CollisionVertexList = [] #Store a list of verticies
        Triangles = [] #List of triangles, each containing indicies of verticies
        CollisionVertexList,Triangles = unpack(ColStream)

            
        mesh = bpy.data.meshes.new("mesh")  # add a new mesh
        obj = bpy.data.objects.new("MyObject", mesh)  # add a new object using the mesh

        scene = bpy.context.scene
        scene.objects.link(obj)  # put the object into the scene (link)
        scene.objects.active = obj  # set as the active object in the scene
        obj.select = True  # select object

        mesh = obj.data
        bm = bmesh.new()
        BMeshVertexList = []
        
        
        for v in CollisionVertexList:
            BMeshVertexList.append(bm.verts.new((v.x,-v.z,v.y)))  # add a new vert
                
        for f in Triangles:
            try: #Try and catch to avoid exception on duplicate triangles. Dodgy...
                MyFace = bm.faces.new((BMeshVertexList[f.vertex_indices[0]],BMeshVertexList[f.vertex_indices[1]],BMeshVertexList[f.vertex_indices[2]]))
                for i in range(0,len(obj.data.materials)): #Scan materials to find match
                    mat = obj.data.materials[i]
                    if f.unknown0 == mat.ColEditor.U0 and f.unknown1 == mat.ColEditor.U1 and f.unknown2 == mat.ColEditor.U2 and f.unknown3 == mat.ColEditor.U3:#Equate unknowns
                        Unknown4AreEqual = (f.unknown4 == mat.ColEditor.U4)
                        Unknown4DontExist = f.unknown4 is None and mat.ColEditor.HasU4 is False #If the unknown4 doesn't exist we need to check for that case
                        if Unknown4AreEqual or Unknown4DontExist:
                            MyFace.material_index = i
                            break #We assigned our material 
                else: #We did not find a material that matched
                    print("new mat")
                    MaterialName = str(f.unknown0)+","+str(f.unknown1)+","+str(f.unknown2)+","+str(f.unknown3)+","+str(f.unknown4)
                    mat = bpy.data.materials.new(name=MaterialName)
                    
                    Magnitude = (f.unknown0**(2) + f.unknown1**(2) + f.unknown2**(2))**(0.5) * (256/256-f.unknown3) #Calculate rgb values
                    Red = f.unknown0/Magnitude
                    Green = f.unknown1/Magnitude
                    Blue = f.unknown2/Magnitude
                    mat.diffuse_color = (Red,Green,Blue)
                    
                    mat.ColEditor.U0 = f.unknown0#Set collision values
                    mat.ColEditor.U1 = f.unknown1
                    mat.ColEditor.U2 = f.unknown2
                    mat.ColEditor.U3 = f.unknown3
                    
                    if f.unknown4 is not None:
                        mat.ColEditor.HasU4 = True
                        mat.ColEditor.U4 = f.unknown4
                    else:
                        mat.ColEditor.HasU4 = False
                        mat.ColEditor.U4 = 0 
                    obj.data.materials.append(mat) #add material to our object
                    MyFace.material_index = len(obj.data.materials) - 1 #Since material was just added it will be the last index
            except:
                continue
        
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
        
        return{'FINISHED'}

class ExportCOL(Operator, ExportHelper): #Operator that exports the collision model into .col file
    """Save a COL file"""
    bl_idname = "export_mesh.col"
    bl_label = "Export COL"
    filter_glob = StringProperty( 
        default="*.col",
        options={'HIDDEN'},
    )#This property filters what you see in the file browser to just .col files

    check_extension = True
    filename_ext = ".col" #This is the extension that the model will have
	
	#To do: add material presets
    
    Scale = FloatProperty(
        name="Scale factor",
        description="Scale the col file by this amount",
        default=1,
    )
	
    def execute(self, context):        # execute() is called by blender when running the operator.
        bpy.ops.object.mode_set (mode = 'OBJECT') #Set mode to be object mode
        VertexList = [] #Store a list of verticies
        Triangles = [] #List of triangles, each containing indicies of verticies
        IndexOffset = 0 #Since each object starts their vertex indicies at 0, we need to shift these indicies once we add elements to the vertex list from various objects
        for Obj in bpy.context.scene.objects: #for all objects
            bm = bmesh.new() #Define new bmesh
            MyMesh = Obj.to_mesh(context.scene, True, 'PREVIEW')#make a copy of the object we can modify freely
            bm.from_mesh(MyMesh) #Add the above copy into the bmesh
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=0, ngon_method=0) #triangulate bmesh

            for Vert in bm.verts:
                VertexList.append(Vertex(Vert.co.x*self.Scale,Vert.co.z*self.Scale,-Vert.co.y*self.Scale)) #add in verts, make sure y is up

            for Face in bm.faces:
                MyTriangle = Triangle()
                MyTriangle.vertex_indices = [Face.verts[0].index + IndexOffset,Face.verts[1].index + IndexOffset,Face.verts[2].index + IndexOffset] #add three vertex indicies

                slot = Obj.material_slots[Face.material_index]
                mat = slot.material.ColEditor
                if mat is not None:
                    MyTriangle.unknown0 = mat.U0
                    MyTriangle.unknown1 = mat.U1
                    MyTriangle.unknown2 = mat.U2
                    MyTriangle.unknown3 = mat.U3
                    if mat.HasU4 == True:
                        MyTriangle.unknown4 = mat.U4
                Triangles.append(MyTriangle) #add triangles
            bm.free()
            del bm
            IndexOffset = len(VertexList)#set offset

        ColStream = open(self.filepath,'wb')
        pack(ColStream,VertexList,Triangles)
        return {'FINISHED'}            # this lets blender know the operator finished successfully.

class CollisionProperties(PropertyGroup): #This defines the UI elements
    U0 = IntProperty(name = "Unknown 0",default=0, min=0, max=255) #Here we put parameters for the UI elements and point to the Update functions
    U1 = IntProperty(name = "Unknown 1",default=0, min=0, max=255)
    U2 = IntProperty(name = "Unknown 2",default=0, min=0, max=255)
    U3 = IntProperty(name = "Unknown 3",default=0, min=0, max=255)#I probably should have made these an array
    HasU4 = BoolProperty(name="Has Unknown 4", default=False)
    U4 = IntProperty(name = "Unknown 4",default=0, min=0, max=65535)

class CollisionPanel(Panel): #This panel houses the UI elements defined in the CollisionProperties
    bl_label = "Edit Collision Values"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
 
    @classmethod
    def poll(cls, context):#stolen from blender
        mat = context.material
        engine = context.scene.render.engine
        return check_material(mat) and (mat.type in {'SURFACE', 'WIRE'})
    
    def draw(self, context):
        mat = context.material.ColEditor
        column1 = self.layout.column(align = True)
        column1.prop(mat,"U0")
        column1.prop(mat,"U1")
        column1.prop(mat,"U2")
        column1.prop(mat,"U3")
        
        column1.prop(mat,"HasU4")
        column2 = self.layout.column(align = True)
        column2.prop(mat,"U4")
        column2.enabled = mat.HasU4 #must have "Has Unknown4" checked
        
       
def check_material(mat):
    if mat is not None:
        if mat.use_nodes:
            if mat.active_node_material is not None:
                return True
            return False
        return True
    return False
    
classes = (ExportCOL,ImportCOL, CollisionPanel,CollisionProperties) #list of classes to register/unregister  
def register():
    for i in classes:
        register_class(i)
    bpy.types.Material.ColEditor = PointerProperty(type=CollisionProperties) #store in the scene
    bpy.types.INFO_MT_file_export.append(menu_export) #Add to export menu
    bpy.types.INFO_MT_file_import.append(menu_import) #Add to import menu
    

def menu_export(self, context):
    self.layout.operator(ExportCOL.bl_idname, text="Collision (.col)")
    
def menu_import(self, context):
    self.layout.operator(ImportCOL.bl_idname, text="Collision (.col)")
    
def unregister():
    for i in classes:
        unregister_class(i)
    bpy.types.INFO_MT_file_export.remove(menu_export)
    bpy.types.INFO_MT_file_import.remove(menu_import)

    

# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()