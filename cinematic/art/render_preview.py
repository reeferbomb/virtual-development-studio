"""Render a representative CPU preview from the actual GLB exports."""
import sys
from pathlib import Path
import bpy
from mathutils import Vector

def point_at(node, point):
    node.rotation_euler = (Vector(point)-node.location).to_track_quat('-Z','Y').to_euler()

def main():
    args=sys.argv[sys.argv.index('--')+1:]
    directory,output=map(Path,args)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for name in ('city','animated_actor'):
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(directory/(name+'.glb')))
        if name=='animated_actor':
            created=set(bpy.data.objects)-before
            for obj in created:
                if obj.parent not in created:
                    obj.location += Vector((0,-1,0))
                    obj.rotation_euler.z += 3.14159
    scene=bpy.context.scene
    scene.frame_set(15)
    scene.render.engine='CYCLES'
    scene.cycles.device='CPU'
    scene.cycles.samples=12
    scene.cycles.use_denoising=True
    scene.render.threads_mode='FIXED'
    scene.render.threads=5
    scene.world.use_nodes=True
    background=scene.world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value=(.12,.20,.36,1)
    background.inputs['Strength'].default_value=.35
    scene.view_settings.exposure=-.45
    bpy.ops.object.camera_add(location=(2.55,-5.7,2.25))
    camera=bpy.context.object
    camera.data.lens=37
    point_at(camera,(0,-.65,1.25))
    scene.camera=camera
    for pos,power,color,size in [((0,-5,7),2000,(.55,.70,1),5),((0,6,5),1800,(.32,.48,1),6),((-3,-1,3.5),720,(1,.48,.19),2),((3,3,4),850,(1,.62,.28),3)]:
        bpy.ops.object.light_add(type='AREA',location=pos)
        light=bpy.context.object
        light.data.energy=power
        light.data.color=color
        light.data.shape='DISK'
        light.data.size=size
        point_at(light,(0,0,1))
    scene.render.resolution_x=960
    scene.render.resolution_y=540
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(output)
    bpy.ops.render.render(write_still=True)
    print('STUDIO_CINEMATIC_RENDER_PASS')

if __name__=='__main__': main()
