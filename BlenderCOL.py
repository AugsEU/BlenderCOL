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

        mesh = bpy.context.object.data
        bm = bmesh.new()
        U0Layer = bm.faces.layers.int.new(CollisionLayer.Unknown0.value) #Create new data layers
        U1Layer = bm.faces.layers.int.new(CollisionLayer.Unknown1.value)
        U2Layer = bm.faces.layers.int.new(CollisionLayer.Unknown2.value)
        U3Layer = bm.faces.layers.int.new(CollisionLayer.Unknown3.value)
        HasU4Layer = bm.faces.layers.int.new(CollisionLayer.HasUnknown4.value)
        U4Layer = bm.faces.layers.int.new(CollisionLayer.Unknown4.value)
        
        BMeshVertexList = []
        
        
        for v in CollisionVertexList:
            BMeshVertexList.append(bm.verts.new((v.x,-v.z,v.y)))  # add a new vert
            
        for f in Triangles:
            try: #Try and catch to avoid exception on duplicate triangles. Dodgy...
                MyFace = bm.faces.new((BMeshVertexList[f.vertex_indices[0]],BMeshVertexList[f.vertex_indices[1]],BMeshVertexList[f.vertex_indices[2]]))
                MyFace[U0Layer] = f.unknown0
                MyFace[U1Layer] = f.unknown1
                MyFace[U2Layer] = f.unknown2
                MyFace[U3Layer] = f.unknown3
                MyFace[U4Layer] = f.unknown4
                if MyFace[U4Layer] is not None:
                    MyFace[HasU4Layer] = True
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
        bm = bmesh.new() #Define new bmesh
        for Obj in bpy.context.scene.objects: #join all objects
            MyMesh = Obj.to_mesh(context.scene, True, 'PREVIEW')#make a copy of the object we can modify freely
            bm.from_mesh(MyMesh) #Add the above copy into the bmesh
        
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=0, ngon_method=0) #triangulate bmesh
        #triangulate_mesh(Mesh)
        U0Layer = bm.faces.layers.int.get(CollisionLayer.Unknown0.value)
        U1Layer = bm.faces.layers.int.get(CollisionLayer.Unknown1.value)
        U2Layer = bm.faces.layers.int.get(CollisionLayer.Unknown2.value)
        U3Layer = bm.faces.layers.int.get(CollisionLayer.Unknown3.value)
        HasU4Layer = bm.faces.layers.int.get(CollisionLayer.HasUnknown4.value)
        U4Layer = bm.faces.layers.int.get(CollisionLayer.Unknown4.value)

        
        for Vert in bm.verts:
            VertexList.append(Vertex(Vert.co.x*self.Scale,Vert.co.z*self.Scale,-Vert.co.y*self.Scale)) #add in verts, make sure y is up

        for Face in bm.faces:
            MyTriangle = Triangle()
            MyTriangle.vertex_indices = [Face.verts[0].index,Face.verts[1].index,Face.verts[2].index] #add three vertex indicies
            if U0Layer is not None:
                MyTriangle.unknown0 = Face[U0Layer]
                MyTriangle.unknown1 = Face[U1Layer]
                MyTriangle.unknown2 = Face[U2Layer]
                MyTriangle.unknown3 = Face[U3Layer]
                if Face[HasU4Layer] != 0:
                    MyTriangle.unknown4 = Face[U4Layer]
            Triangles.append(MyTriangle) #add triangles
        
        ColStream = open(self.filepath,'wb')
        pack(ColStream,VertexList,Triangles)
        return {'FINISHED'}            # this lets blender know the operator finished successfully.
        
class CollisionLayer(Enum): #This stores the data layer names that each Unknown will be on.
    Unknown0 = "CollisionEditorUnknown0"
    Unknown1 = "CollisionEditorUnknown1"
    Unknown2 = "CollisionEditorUnknown2" #For example Unknown2 is stored on a data layer called "CollisionEditorUnknown2"
    Unknown3 = "CollisionEditorUnknown3" 
    HasUnknown4 = "CollisionEditorHasUnknown4" #This layer is an integer because boolean layers don't exist
    Unknown4 = "CollisionEditorUnknown4"
        
def U0Update(self, context): #These functions are called when the UI elements change
    ChangeValuesOfSelection(CollisionLayer.Unknown0.value,bpy.context.scene.ColEditor.U0)
    return

def U1Update(self, context): #It would be nice to call ChangeValuesOfSelection directly but Update Functions can't have parameters as far as I am aware
    ChangeValuesOfSelection(CollisionLayer.Unknown1.value,bpy.context.scene.ColEditor.U1)
    return

def U2Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown2.value,bpy.context.scene.ColEditor.U2)
    return
    
def U3Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown3.value,bpy.context.scene.ColEditor.U3)
    return
    
def HasU4Update(self, context):
    ToSet = 1 if bpy.context.scene.ColEditor.HasU4 else 0 #In this case a TRUE value is represented by a 1 and FALSE by 0
    ChangeValuesOfSelection(CollisionLayer.HasUnknown4.value,ToSet)
    return

def U4Update(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown4.value,bpy.context.scene.ColEditor.U4)
    return
  
  
class CollisionProperties(PropertyGroup): #This defines the UI elements
    U0 = IntProperty(name = "Unknown 0",default=0, min=0, max=255, update = U0Update) #Here we put parameters for the UI elements and point to the Update functions
    U1 = IntProperty(name = "Unknown 1",default=0, min=0, max=255, update = U1Update)
    U2 = IntProperty(name = "Unknown 2",default=0, min=0, max=255, update = U2Update)
    U3 = IntProperty(name = "Unknown 3",default=0, min=0, max=255, update = U3Update)#I probably should have made these an array
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
            EnableInitial = True #We must be in edit mode to initalise values
            obj = bpy.context.scene.objects.active #This method might be quite taxing
            bm = bmesh.from_edit_mesh(obj.data)
            U0Layer = bm.faces.layers.int.get(CollisionLayer.Unknown0.value) #Check if this layer exists
            if U0Layer is not None: #If the model has collision values
                EnableColumns = True #Then we enabled editing the values
            del bm
            del obj
            
        
        
        row = self.layout.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("init.colvalues", text='Initialise values') #Here we put the UI elements defined in CollisionProperties into rows and columns
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
        column2.enabled = bpy.context.scene.ColEditor.HasU4 and EnableColumns #Collision values must exist AND we must have "Has Unknown4" checked
        
        
class InitialValues(Operator): #This creates the data layers that store the collision values
    bl_idname = "init.colvalues"
    bl_label = "Initialise Collision Values"
    
    def execute(self, context):
        obj = bpy.context.scene.objects.active
        bm = bmesh.from_edit_mesh(obj.data)
        
        bm.faces.layers.int.new(CollisionLayer.Unknown0.value) #Uses Enum to get names
        bm.faces.layers.int.new(CollisionLayer.Unknown1.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown2.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown3.value)
        bm.faces.layers.int.new(CollisionLayer.HasUnknown4.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown4.value)
        return{'FINISHED'}        

def ChangeValuesOfSelection(ValueToChange,ValueToSet):
    obj = bpy.context.scene.objects.active
    bm = bmesh.from_edit_mesh(obj.data)
    selected_faces = [f for f in bm.faces if f.select] #This gets an array of selected faces
    #get the custom data layer by its name
    my_id = bm.faces.layers.int[ValueToChange]

    for face in bm.faces:
        if(face.select == True):
            face[my_id] = ValueToSet
            if ValueToChange == CollisionLayer.Unknown4.value: #If you somehow edit Unknown4 when HasUnknown4 is off, like with a group selection, make sure to turn it on
                HasU4Layer = bm.faces.layers.int.get(CollisionLayer.HasUnknown4.value)
                face[HasU4Layer] = 1
                

    bmesh.update_edit_mesh(obj.data, False,False) #Update mesh with new values    
    
    
class UpdateUI(bpy.types.Operator): #This function will put the values of the selected face into the UI elements
    bl_idname = "ui.update"
    bl_label = "Updates the UI with values from selection"


    def execute(self, context):
        if(bpy.context.object.mode == 'EDIT'):
            obj = bpy.context.scene.objects.active
            bm = bmesh.from_edit_mesh(obj.data)
            U0Layer = bm.faces.layers.int.get(CollisionLayer.Unknown0.value) #Check if this layer exists
            if U0Layer is not None: #If the model has collision values
                selected_faces = [f for f in bm.faces if f.select]
                if len(selected_faces) > 0:
                    bpy.context.scene.ColEditor["U0"] = selected_faces[0][U0Layer] #This is why they should have been an array
                    
                    U1Layer = bm.faces.layers.int.get(CollisionLayer.Unknown1.value) #Get name of data layer
                    bpy.context.scene.ColEditor["U1"] = selected_faces[0][U1Layer] #Set UI element to value in selected face
                    
                    U2Layer = bm.faces.layers.int.get(CollisionLayer.Unknown2.value)
                    bpy.context.scene.ColEditor["U2"] = selected_faces[0][U2Layer] #We call it like this so that we don't call the update function. Otherwise selecting multiple faces would set them all equal
                    
                    U3Layer = bm.faces.layers.int.get(CollisionLayer.Unknown3.value)
                    bpy.context.scene.ColEditor["U3"] = selected_faces[0][U3Layer] #We choose index 0 but it doesn't really matter. Unfortunetly you can't get int properties to display "--" used, for example, when there are different unknown0 values across the selected faces
                    
                    HasU4Layer = bm.faces.layers.int.get(CollisionLayer.HasUnknown4.value)
                    bpy.context.scene.ColEditor["HasU4"] = False if selected_faces[0][HasU4Layer]  == 0 else True 
                    
                    U4Layer = bm.faces.layers.int.get(CollisionLayer.Unknown4.value)
                    bpy.context.scene.ColEditor["U4"] = selected_faces[0][U4Layer]

        return {'FINISHED'}
    
    
classes = (ExportCOL,ImportCOL, CollisionPanel,InitialValues,CollisionProperties,UpdateUI) #list of classes to register/unregister  
addon_keymaps = []  
def register():
    for i in classes:
        register_class(i)
    Scene.ColEditor = PointerProperty(type=CollisionProperties) #store in the scene
    #handle the keymap
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new("object.updateui", 'SELECTMOUSE', 'PRESS', any=True)
    addon_keymaps.append(km)
    
    bpy.types.INFO_MT_file_export.append(menu_export) #Add to export menu
    bpy.types.INFO_MT_file_import.append(menu_import) #Add to export menu
    

def menu_export(self, context):
    self.layout.operator(ExportCOL.bl_idname, text="Collision (.col)")
    
def menu_import(self, context):
    self.layout.operator(ImportCOL.bl_idname, text="Collision (.col)")
    
def unregister():
    for i in classes:
        unregister_class(i)
    bpy.types.INFO_MT_file_export.remove(menu_export)
    bpy.types.INFO_MT_file_import.remove(menu_import)
    # handle the keymap
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    # clear the list
    addon_keymaps.clear()
    



# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()