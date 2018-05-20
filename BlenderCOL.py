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
    CollisionType = uint16 #Properties of collision. e.g. is it water? or what?
    triangle_count = uint16
    
    __padding__ = Padding(1,b'\x00') #Group flags, set them to 0 here
    has_ColParameter = bool8 #Set 0x0001 to 1 if we have ColParameter values so the game doesn't ignore it
    __padding__ = Padding(2)#Actual padding
    vertex_index_offset = uint32
    TerrainType_offset = uint32 # 0-18,20,21,23,24,27-31
    unknown_offset = uint32 # 0-27
    ColParameter_offset = uint32 # 0,1,2,3,4,8,255,6000,7500,7800,8000,8400,9000,10000,10300,12000,14000,17000,19000,20000,21000,22000,27500,30300


class Triangle:

    def __init__(self):
        self.vertex_indices = None
        self.ColType = 0
        self.TerrainType = 0
        self.unknown = 0
        self.ColParameter = None

    @property
    def has_ColParameter(self):
        return self.ColParameter is not None


def pack(stream,vertices,triangles): #pack triangles into col file
    groups = []

    for triangle in triangles:
        for group in groups: #for each triangle add to appropriate group
            if triangle.ColType != group.CollisionType: continue #break out of loop to next cycle
            group.triangles.append(triangle)
            break
        else: #if no group has been found
            group = Group() #create a new group
            group.CollisionType = triangle.ColType
            group.has_ColParameter = triangle.has_ColParameter
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
        group.TerrainType_offset = stream.tell()
        for triangle in group.triangles:
            uint8.pack(stream,triangle.TerrainType)

    for group in groups:
        group.unknown_offset = stream.tell()
        for triangle in group.triangles:
            uint8.pack(stream,triangle.unknown)

    for group in groups:
        if not group.has_ColParameter:
            group.ColParameter_offset = 0
        else:
            group.ColParameter_offset = stream.tell()
            for triangle in group.triangles:
                uint16.pack(stream,triangle.ColParameter)

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
            triangle.ColType = group.CollisionType

    for group in groups:
        stream.seek(group.vertex_index_offset)
        for triangle in group.triangles:
            triangle.vertex_indices = [uint16.unpack(stream) for _ in range(3)]

    for group in groups:
        stream.seek(group.TerrainType_offset)
        for triangle in group.triangles:
            triangle.TerrainType = uint8.unpack(stream)

    for group in groups:
        stream.seek(group.unknown_offset)
        for triangle in group.triangles:
            triangle.unknown = uint8.unpack(stream)

    for group in groups:
        if not group.has_ColParameter: continue
        stream.seek(group.ColParameter_offset)
        for triangle in group.triangles:
            triangle.ColParameter = uint16.unpack(stream)

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
        ColTypeLayer = bm.faces.layers.int.new(CollisionLayer.ColType.value) #Create new data layers
        TerrainTypeLayer = bm.faces.layers.int.new(CollisionLayer.TerrainType.value)
        UnknownFieldLayer = bm.faces.layers.int.new(CollisionLayer.Unknown.value)
        HasColParameterFieldLayer = bm.faces.layers.int.new(CollisionLayer.HasColParameter.value)
        ColParameterFieldLayer = bm.faces.layers.int.new(CollisionLayer.ColParameter.value)
        
        BMeshVertexList = []
        
        
        for v in CollisionVertexList:
            BMeshVertexList.append(bm.verts.new((v.x,-v.z,v.y)))  # add a new vert
            
        for f in Triangles:
            try: #Try and catch to avoid exception on duplicate triangles. Dodgy...
                MyFace = bm.faces.new((BMeshVertexList[f.vertex_indices[0]],BMeshVertexList[f.vertex_indices[1]],BMeshVertexList[f.vertex_indices[2]]))
                MyFace[ColTypeLayer] = f.ColType
                MyFace[TerrainTypeLayer] = f.TerrainType
                MyFace[UnknownFieldLayer] = f.Unknown
                MyFace[ColParameterFieldLayer] = f.ColParameter
                if MyFace[ColParameterFieldLayer] is not None:
                    MyFace[HasColParameterFieldLayer] = True
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
        ColTypeLayer = bm.faces.layers.int.get(CollisionLayer.ColType.value)
        TerrainTypeLayer = bm.faces.layers.int.get(CollisionLayer.TerrainType.value)
        UnknownFieldLayer = bm.faces.layers.int.get(CollisionLayer.Unknown.value)
        HasColParameterFieldLayer = bm.faces.layers.int.get(CollisionLayer.HasColParameter.value)
        ColParameterFieldLayer = bm.faces.layers.int.get(CollisionLayer.ColParameter.value)

        
        for Vert in bm.verts:
            VertexList.append(Vertex(Vert.co.x*self.Scale,Vert.co.z*self.Scale,-Vert.co.y*self.Scale)) #add in verts, make sure y is up

        for Face in bm.faces:
            MyTriangle = Triangle()
            MyTriangle.vertex_indices = [Face.verts[0].index,Face.verts[1].index,Face.verts[2].index] #add three vertex indicies
            if ColTypeLayer is not None:
                MyTriangle.ColType = Face[ColTypeLayer]
                MyTriangle.TerrainType = Face[TerrainTypeLayer]
                MyTriangle.Unknown = Face[UnknownFieldLayer]
                if Face[HasColParameterFieldLayer] != 0:
                    MyTriangle.ColParameter = Face[ColParameterFieldLayer]
            Triangles.append(MyTriangle) #add triangles
        
        ColStream = open(self.filepath,'wb')
        pack(ColStream,VertexList,Triangles)
        return {'FINISHED'}            # this lets blender know the operator finished successfully.
        
class CollisionLayer(Enum): #This stores the data layer names that each Unknown will be on.
    ColType = "CollisionEditorColType"
    TerrainType = "CollisionEditorTerrainType" #For example TerrainType is stored on a data layer called "CollisionEditorTerrainType"
    Unknown = "CollisionEditorUnknown" 
    HasColParameter = "CollisionEditorHasColParameter" #This layer is an integer because boolean layers don't exist
    ColParameter = "CollisionEditorColParameter"
        
def ColTypeUpdate(self, context): #These functions are called when the UI elements change
    ChangeValuesOfSelection(CollisionLayer.ColType.value,bpy.context.scene.ColEditor.ColType)
    return


def TerrainTypeUpdate(self, context):
    ChangeValuesOfSelection(CollisionLayer.TerrainType.value,bpy.context.scene.ColEditor.TerrainType)
    return
    
def UnknownFieldUpdate(self, context):
    ChangeValuesOfSelection(CollisionLayer.Unknown.value,bpy.context.scene.ColEditor.UnknownField)
    return
    
def HasColParameterFieldUpdate(self, context):
    ToSet = 1 if bpy.context.scene.ColEditor.HasColParameterField else 0 #In this case a TRUE value is represented by a 1 and FALSE by 0
    ChangeValuesOfSelection(CollisionLayer.HasColParameter.value,ToSet)
    return

def ColParameterFieldUpdate(self, context):
    ChangeValuesOfSelection(CollisionLayer.ColParameter.value,bpy.context.scene.ColEditor.ColParameterField)
    return
   
class CollisionProperties(PropertyGroup): #This defines the UI elements
    ColType = IntProperty(name = "Collision type",default=0, min=0, max=65535,update = ColTypeUpdate) #Here we put parameters for the UI elements and point to the Update functions
    TerrainType = IntProperty(name = "Sound",default=0, min=0, max=255,update = TerrainTypeUpdate)
    UnknownField = IntProperty(name = "Unknown",default=0, min=0, max=255,update =  UnknownFieldUpdate)#I probably should have made these an array
    HasColParameterField = BoolProperty(name="Has Parameter", default=False,update = HasColParameterFieldUpdate)
    ColParameterField = IntProperty(name = "Parameter",default=0, min=0, max=65535,update = ColParameterFieldUpdate)

class CollisionPanel(Panel): #This panel houses the UI elements defined in the CollisionProperties
    bl_label = "Edit Collision Values"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
 
    @classmethod
    def poll(cls, context):
        # Only allow in edit mode for a selected mesh.
        return context.mode == "EDIT_MESH" and context.object is not None and context.object.type == "MESH"
 
    def draw(self, context):
        EnableColumns = False #Boolean is true means we will enable the columns
        if(bpy.context.object.mode == 'EDIT'):
            obj = bpy.context.scene.objects.active #This method might be quite taxing
            bm = bmesh.from_edit_mesh(obj.data)
            ColTypeLayer = bm.faces.layers.int.get(CollisionLayer.ColType.value) #Check if this layer exists
            if ColTypeLayer is not None: #If the model has collision values
                EnableColumns = True #Then we enabled editing the values
            del bm
            del obj
            
        
        
        row = self.layout.row(align=True)
        row.alignment = 'EXPAND'
        row.operator("init.colvalues", text='Initialise values') #Here we put the UI elements defined in CollisionProperties into rows and columns
        
        
        column1 = self.layout.column(align = True)
        column1.prop(bpy.context.scene.ColEditor, "ColType")
        column1.prop(bpy.context.scene.ColEditor, "TerrainType")
        column1.prop(bpy.context.scene.ColEditor, "UnknownField")
        column1.enabled = EnableColumns
        
        column1.prop(bpy.context.scene.ColEditor, "HasColParameterField")
        column2 = self.layout.column(align = True)
        column2.prop(bpy.context.scene.ColEditor, "ColParameterField")
        column2.enabled = bpy.context.scene.ColEditor.HasColParameterField and EnableColumns #Collision values must exist AND we must have "Has ColParameter" checked
        
        
class InitialValues(Operator): #This creates the data layers that store the collision values
    bl_idname = "init.colvalues"
    bl_label = "Initialise Collision Values"
    
    def execute(self, context):
        obj = bpy.context.scene.objects.active
        bm = bmesh.from_edit_mesh(obj.data)
        
        bm.faces.layers.int.new(CollisionLayer.ColType.value) #Uses Enum to get names
        bm.faces.layers.int.new(CollisionLayer.TerrainType.value)
        bm.faces.layers.int.new(CollisionLayer.Unknown.value)
        bm.faces.layers.int.new(CollisionLayer.HasColParameter.value)
        bm.faces.layers.int.new(CollisionLayer.ColParameter.value)
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
            if ValueToChange == CollisionLayer.ColParameter.value: #If you somehow edit ColParameter when HasColParameter is off, like with a group selection, make sure to turn it on
                HasColParameterFieldLayer = bm.faces.layers.int.get(CollisionLayer.HasColParameter.value)
                face[HasColParameterFieldLayer] = 1
                

    bmesh.update_edit_mesh(obj.data, False,False) #Update mesh with new values    
    
@persistent
def UpdateUI(scene):
    obj = scene.objects.active
    if(obj.mode == 'EDIT' and obj.type == 'MESH'):
            bm = bmesh.from_edit_mesh(obj.data)
            ColTypeLayer = bm.faces.layers.int.get(CollisionLayer.ColType.value) #Check if this layer exists
            if ColTypeLayer is not None: #If the model has collision values
                face = bm.faces.active
                if face is not None:
                    bpy.context.scene.ColEditor["ColType"] = face[ColTypeLayer] #This is why they should have been an array
                    
                    TerrainTypeLayer = bm.faces.layers.int.get(CollisionLayer.TerrainType.value)
                    bpy.context.scene.ColEditor["TerrainType"] = face[TerrainTypeLayer] #We call it like this so that we don't call the update function. Otherwise selecting multiple faces would set them all equal
                    
                    UnknownFieldLayer = bm.faces.layers.int.get(CollisionLayer.Unknown.value)
                    bpy.context.scene.ColEditor["UnknownField"] = face[UnknownFieldLayer] #We choose index 0 but it doesn't really matter. Unfortunetly you can't get int properties to display "--" used, for example, when there are different ColType values across the selected faces
                    
                    HasColParameterFieldLayer = bm.faces.layers.int.get(CollisionLayer.HasColParameter.value)
                    bpy.context.scene.ColEditor["HasColParameterField"] = False if face[HasColParameterFieldLayer]  == 0 else True 
                    
                    ColParameterFieldLayer = bm.faces.layers.int.get(CollisionLayer.ColParameter.value)
                    bpy.context.scene.ColEditor["ColParameterField"] = face[ColParameterFieldLayer]
    return None    
    
    
classes = (ExportCOL,ImportCOL, CollisionPanel,InitialValues,CollisionProperties) #list of classes to register/unregister  
def register():
    for i in classes:
        register_class(i)
    Scene.ColEditor = PointerProperty(type=CollisionProperties) #store in the scene
    bpy.app.handlers.scene_update_post.append(UpdateUI)
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
    if UpdateUI in bpy.app.handlers.render_post:
        bpy.app.handlers.render_complete.remove(UpdateUI)#remove handlers

    

# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()