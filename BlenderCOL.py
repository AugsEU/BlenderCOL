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
import random
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

class BlenderCollisionGroup:
    MaterialList = [] #stores material indicies
    CollisionType = uint16
    GroupFlags = uint16
    
    def __init__(self,MatList,ColType):
        self.MaterialList = MatList
        self.CollisionType=ColType
        
    def ValidateGroup(): #Removes any materials that shouldn't be in the list
        for mat in self.MaterialList:
            if mat is None:
                self.MaterialList.remove(mat)
                continue
            if mat.ColEditor is None: #If material doesn't have collision values remove it
                self.MaterialList.remove(mat)
                continue
            if mat.ColEditor.ColType != self.CollisionType: #We need to do this after the above statement to avoid an exception
                self.MaterialList.remove(mat)
    
    def AddMaterial(Mat):
        if mat.ColEditor.ColType == self.CollisionType:
            self.MaterialList.append(Mat)
            return "Material added"
        return "Not the right collision type"
        
    def RemoveMaterial(Mat):
        if Mat in self.MaterialList:
            MaterialList.remove(Mat)
         
        
        
        
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
                    if f.ColType == mat.ColEditor.ColType and f.TerrainType == mat.ColEditor.TerrainType and f.unknown == mat.ColEditor.UnknownField:#Equate unknowns
                        ColParameterAreEqual = (f.ColParameter == mat.ColEditor.ColParameterField)
                        ColParameterDontExist = f.ColParameter is None and mat.ColEditor.HasColParameterField is False #If the ColParameter doesn't exist we need to check for that case
                        if ColParameterAreEqual or ColParameterDontExist:
                            MyFace.material_index = i
                            break #We assigned our material 
                else: #We did not find a material that matched
                    MaterialName = str(f.ColType) + "," + str(f.TerrainType) + "," + str(f.unknown) + "," + str(f.ColParameter)
                    mat = bpy.data.materials.new(name=MaterialName)
                    
                    random.seed(hash(MaterialName)) #Not actually random
                    Red = random.random()
                    Green = random.random()
                    Blue = random.random()
                    mat.diffuse_color = (Red,Green,Blue)
                    
                    mat.ColEditor.ColType = f.ColType#Set collision values
                    mat.ColEditor.TerrainType = f.TerrainType
                    mat.ColEditor.UnknownField = f.unknown
                    
                    if f.ColParameter is not None:
                        mat.ColEditor.HasColParameterField = True
                        mat.ColEditor.ColParameterField = f.ColParameter
                    else:
                        mat.ColEditor.HasColParameterField = False
                        mat.ColEditor.ColParameterField = 0 
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
                    MyTriangle.ColType = mat.ColType
                    MyTriangle.TerrainType = mat.TerrainType
                    MyTriangle.unknown = mat.UnknownField
                    if mat.HasColParameterField == True:
                        MyTriangle.ColParameter = mat.ColParameterField
                Triangles.append(MyTriangle) #add triangles
            bm.free()
            del bm
            IndexOffset = len(VertexList)#set offset

        ColStream = open(self.filepath,'wb')
        pack(ColStream,VertexList,Triangles)
        return {'FINISHED'}            # this lets blender know the operator finished successfully.

class CollisionProperties(PropertyGroup): #This defines the UI elements
    ColType = IntProperty(name = "Collision type",default=0, min=0, max=65535) #Here we put parameters for the UI elements and point to the Update functions
    TerrainType = IntProperty(name = "Sound",default=0, min=0, max=255)
    UnknownField = IntProperty(name = "Unknown",default=0, min=0, max=255)#I probably should have made these an array
    HasColParameterField = BoolProperty(name="Has Parameter", default=False)
    ColParameterField = IntProperty(name = "Parameter",default=0, min=0, max=65535)

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
        column1.prop(mat,"ColType")
        column1.prop(mat,"TerrainType")
        column1.prop(mat,"UnknownField")
        
        column1.prop(mat,"HasColParameterField")
        column2 = self.layout.column(align = True)
        column2.prop(mat,"ColParameterField")
        column2.enabled = mat.HasColParameterField #must have "Has ColParameter" checked
     
def check_material(mat):
    if mat is not None:
        if mat.use_nodes:
            if mat.active_node_material is not None:
                return True
            return False
        return True
    return False
     
class MESH_UL_GroupsList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        self.use_filter_show = True

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            split = layout.split(0.1)
            split.prop(item, "Name", text="", emboss=False)
            split = split.split(0.3)
            split.prop(item, "ColType", text="", emboss=False)

        elif self.layout_type in {'GRID'}:
            pass

    # Called once to filter/reorder items.
    def filter_items(self, context, data, propname):#magic

        col = getattr(data, propname)
        filter_name = self.filter_name.lower()

        flt_flags = [self.bitflag_filter_item if any(
                filter_name in filter_set for filter_set in (
                    str(i), item.Name.lower()
                )
            )
            else 0 for i, item in enumerate(col, 1)
        ]

        if self.use_filter_sort_alpha:
            flt_neworder = [x[1] for x in sorted(
                    zip(
                        [x[0] for x in sorted(enumerate(col), key=lambda x: x[1].Name)],
                        range(len(col))
                    )
                )
            ]
        else:
            flt_neworder = []

        return flt_flags, flt_neworder
   

def ListClick(self, context):
    print(bpy.context.scene.CollisionGroupList[0].Name)
   
class GroupsPanel(Panel):
    bl_label = "Edit Collision Groups"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    
    def draw(self, context):
        layout = self.layout
        ob = context.object
        if ob:
            row = layout.row()
            row.template_list("MESH_UL_GroupsList", "", context.scene, "CollisionGroupList", context.scene, "CollisionGroup_idx")

            col = row.column(align=True)
            col.operator("colgroup.add", icon='ZOOMIN', text="")
            col.operator("colgroup.remove", icon='ZOOMOUT', text="")

            if len(context.scene.CollisionGroupList) > context.scene.CollisionGroup_idx:
                print(SpecialGroupList[context.scene.CollisionGroup_idx])
        
        
  
      
class GroupsCollection(bpy.types.PropertyGroup):
    Name = bpy.props.StringProperty()
    ColType = bpy.props.IntProperty()
    ColGroup = BlenderCollisionGroup([],0)
  
class AddGroup(bpy.types.Operator):
    bl_idname = "colgroup.add"
    bl_label = "Add group"

    def execute(self, context):
        NewBlenderGroup = BlenderCollisionGroup([],0)
        item = bpy.context.scene.CollisionGroupList.add()
        item.Name = "Untitled"
        item.ColType = 0
        global SpecialGroupList
        SpecialGroupList.append(NewBlenderGroup)
        return {'FINISHED'}
  
class RemoveGroup(bpy.types.Operator):
    bl_idname = "colgroup.remove"
    bl_label = "Remove group"

    def execute(self, context):
        bpy.context.scene.CollisionGroupList.remove(bpy.context.scene.CollisionGroup_idx)
        global SpecialGroupList
        SpecialGroupList.pop(bpy.context.scene.CollisionGroup_idx)
        return {'FINISHED'}
        

classes = (ExportCOL,ImportCOL, CollisionPanel,CollisionProperties,GroupsPanel,AddGroup,RemoveGroup,GroupsCollection,MESH_UL_GroupsList) #list of classes to register/unregister  
def register():
    for i in classes:
        register_class(i)
    bpy.types.Material.ColEditor = PointerProperty(type=CollisionProperties) #store in the scene
    bpy.types.INFO_MT_file_export.append(menu_export) #Add to export menu
    bpy.types.INFO_MT_file_import.append(menu_import) #Add to import menu
    
    Scene.CollisionGroupList = bpy.props.CollectionProperty(type=GroupsCollection)
    Scene.CollisionGroup_idx = bpy.props.IntProperty(default=0)
    

def menu_export(self, context):
    self.layout.operator(ExportCOL.bl_idname, text="Collision (.col)")
    
def menu_import(self, context):
    self.layout.operator(ImportCOL.bl_idname, text="Collision (.col)")
    
def unregister():
    for i in classes:
        unregister_class(i)
    bpy.types.INFO_MT_file_export.remove(menu_export)
    bpy.types.INFO_MT_file_import.remove(menu_import)
    del Scene.CollisionGroupList
    del Scene.CollisionGroup_idx

    

# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()