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
from enum import Enum
from btypes.big_endian import *
from bpy.types import PropertyGroup, Panel, Scene, Operator
from bpy.utils import register_class, unregister_class
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

class ExportCOL(Operator, ExportHelper):
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
        
class CollisionLayer(Enum):
    Unknown0 = "CollisionEditorUnknown0"
    Unknown1 = "CollisionEditorUnknown1"
    Unknown2 = "CollisionEditorUnknown2"
    Unknown3 = "CollisionEditorUnknown3"
    HasUnknown4 = "CollisionEditorHasUnknown4"
    Unknown4 = "CollisionEditorUnknown4"
        
def U0Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown0.value)
    self["U3"]+=1
    return

def U1Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown1.value)
    return

def U2Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown2.value)
    return
    
def U3Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown3.value)
    print("Bobson")
    return
    
def HasU4Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.HasUnknown4.value)
    return

def U4Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown4.value)
    return
    
class CollisionProperties(PropertyGroup): #This defines the UI elements
    U0 = IntProperty(name = "Unknown 0",default=0, min=0, max=255, update = U0Update)
    U1 = IntProperty(name = "Unknown 1",default=0, min=0, max=255, update = U1Update)
    U2 = IntProperty(name = "Unknown 2",default=0, min=0, max=255, update = U2Update)
    U3 = IntProperty(name = "Unknown 3",default=0, min=0, max=255, update = U3Update)
    HasU4 = BoolProperty(name="Has Unknown 4", default=False, update = HasU4Update)
    U4 = IntProperty(name = "Unknown 4",default=0, min=0, max=65535, update = U4Update)

class CollisionPanel(Panel): #This panel houses the UI elements defined in the CollisionProperties
    bl_label = "Edit Collision Values"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
 
    def draw(self, context):
        EnableColumns = False #Boolean is true means we will enable the columns
        EnableInitial = False #Only allow initialise in edit mode
        if(bpy.context.object.mode == 'EDIT'):
            EnableInitial = True
            obj = bpy.context.scene.objects.active #This method might be quite taxing
            bm = bmesh.from_edit_mesh(obj.data)
            U0Layer = bm.faces.layers.int.get(CollisionLayer.Unknown0.value) #Check if this layer exists
            if U0Layer is not None: #If the model has collision values
                EnableColumns = True
            del bm
            del obj
            
        
        
        row = self.layout.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("init.colvalues", text='Initialise values')
        row.enabled = EnableInitial
        
        
        column1 = self.layout.column(align = True)
        column1.prop(bpy.context.scene.ColEditor, "U0")
        column1.prop(bpy.context.scene.ColEditor, "U1")
        column1.prop(bpy.context.scene.ColEditor, "U2")
        column1.prop(bpy.context.scene.ColEditor, "U3")
        column1.enabled = EnableColumns
        
        column1.prop(bpy.context.scene.ColEditor, "HasU4")
        column2 = self.layout.column(align = True)
        column2.prop(bpy.context.scene.ColEditor, "U4")
        column2.enabled = bpy.context.scene.ColEditor.HasU4 and EnableColumns
        
        
class InitialValues(Operator):
    bl_idname = "init.colvalues"
    bl_label = "Initialise Collision Values"
    
    def execute(self, context):
        obj = bpy.context.scene.objects.active
        bm = bmesh.from_edit_mesh(obj.data)
        
        bm.faces.layers.int.new(CollisionLayer.Unknown0.value) #create layers to store collision values
        bm.faces.layers.int.new(CollisionLayer.Unknown1.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown2.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown3.value)
        bm.faces.layers.int.new(CollisionLayer.HasUnknown4.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown4.value)
        return{'FINISHED'}        
    
def ChangeValuesOfSelection(ValueToChange):
    obj = bpy.context.scene.objects.active
    bm = bmesh.from_edit_mesh(obj.data)
    selected_faces = [f for f in bm.faces if f.select]
    #get the custom data layer by its name
    my_id = bm.faces.layers.int[ValueToChange]
    
    ValueToSet = 0
    if ValueToChange == CollisionLayer.Unknown0.value:
        ValueToSet = bpy.context.scene.ColEditor.U0
    elif ValueToChange == CollisionLayer.Unknown1.value:
        ValueToSet = bpy.context.scene.ColEditor.U1
    elif ValueToChange == CollisionLayer.Unknown2.value:
        ValueToSet = bpy.context.scene.ColEditor.U2
    elif ValueToChange == CollisionLayer.Unknown3.value:
        ValueToSet = bpy.context.scene.ColEditor.U3
    elif ValueToChange == CollisionLayer.HasUnknown4.value:
        ValueToSet = 1 if bpy.context.scene.ColEditor.HasU4 else 0
    elif ValueToChange == CollisionLayer.Unknown4.value:
        ValueToSet = bpy.context.scene.ColEditor.U4


    for face in bm.faces:
        if(face.select == True):
            face[my_id] = ValueToSet
            if ValueToChange == CollisionLayer.Unknown4.value: #If you somehow edit Unknown4 when HasUnknown4 is off, like with a group selection, make sure to turn it on
                face[CollisionLayer.HasUnknown4.value] = 1

    bmesh.update_edit_mesh(obj.data, False,False)    
    

    
class UpdateUI(bpy.types.Operator):
    bl_idname = "object.updateui"
    bl_label = "Simple Object Operator"


    def execute(self, context):
        if(bpy.context.object.mode == 'EDIT'):
            obj = bpy.context.scene.objects.active #This method might be quite taxing
            bm = bmesh.from_edit_mesh(obj.data)
            U0Layer = bm.faces.layers.int.get(CollisionLayer.Unknown0.value) #Check if this layer exists
            if U0Layer is not None: #If the model has collision values
                selected_faces = [f for f in bm.faces if f.select]
                bpy.context.scene.ColEditor.U0 = selected_faces[0][U0Layer]
        return {'FINISHED'}
    
    
classes = (ExportCOL, CollisionPanel,InitialValues,CollisionProperties,UpdateUI) #list of classes to register/unregister  
user_keymaps = []  
def register():
    for i in classes:
        register_class(i)
    Scene.ColEditor = PointerProperty(type=CollisionProperties) #store in the scene
    #handle the keymap
    wm = bpy.context.window_manager
    km = wm.keyconfigs.user.keymaps.new(name='3D View', space_type='VIEW_3D')

    kmi = km.keymap_items.new("object.updateui", 'SELECTMOUSE', 'PRESS', any=True)

    user_keymaps.append((km, kmi))
    bpy.types.INFO_MT_file_export.append(menu_func)
    

def menu_func(self, context):
    self.layout.operator(ExportCOL.bl_idname, text="Collision (.col)")
    
def unregister():
    for i in classes:
        unregister_class(i)
    
    #handle the keymap
    for km, kmi in user_keymaps:
        km.keymap_items.remove(kmi)
    user_keymaps.clear()
    
    bpy.types.INFO_MT_file_export.remove(menu_func)


# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()