"""Optional developer blueprint preview (Pillow required), not a game render."""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render(spec, output, route=None):
    image = Image.new("RGB", (1440, 1040), "#101a23")
    draw = ImageDraw.Draw(image)
    def font(size, bold=False):
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    draw.text((46, 36), "STUDIO // WORLD FACTORY", fill="#77d9c7", font=font(25, True))
    draw.text((46, 77), spec["id"].replace("_", " ").upper(), fill="#f0f6fa", font=font(44, True))
    t = spec["terrain"]
    width, depth = t["width"], t["depth"]
    scale = min(940 / width, 760 / depth)
    ox, oy = 45 + 470, 178 + 380
    def pt(x, z):
        return (ox + x * scale, oy + z * scale)
    def bounds(x, z, sx, sz):
        return [pt(x-sx/2, z-sz/2), pt(x+sx/2, z+sz/2)]
    draw.rectangle(bounds(0, 0, width, depth), fill="#293a3e", outline="#78909c", width=4)
    flat = t["flat_radius"]
    draw.rectangle(bounds(0, 0, flat*2, flat*2), fill="#293f42", outline="#579489", width=2)
    for x in range(math.ceil(-width/2), math.floor(width/2)+1):
        if x % 2 == 0:
            draw.line([pt(x, -depth/2), pt(x, depth/2)], fill="#355156")
    for z in range(math.ceil(-depth/2), math.floor(depth/2)+1):
        if z % 2 == 0:
            draw.line([pt(-width/2, z), pt(width/2, z)], fill="#355156")
    for x in range(math.ceil(-width/2), math.floor(width/2)+1):
        if x % 5 == 0:
            px,py=pt(x, -depth/2)
            draw.text((px-12,py-27),str(x),fill="#a3b7bf",font=font(15))
    for z in range(math.ceil(-depth/2), math.floor(depth/2)+1):
        if z % 5 == 0:
            px,py=pt(-width/2,z)
            draw.text((px+5,py+5),str(z),fill="#a3b7bf",font=font(15))
    sx,_,sz=spec["spawn"]
    gx,_,gz=spec["goal"]
    p1, p2 = pt(sx,sz), pt(gx,gz)
    draw.line([pt(p[0],p[2]) for p in route] if route else [p1,p2],fill="#78e0ac",width=5)
    for label,xy,color in (("SPAWN",p1,"#68c0ff"),("GOAL",p2,"#78e0ac")):
        x,y=xy
        draw.ellipse((x-15,y-15,x+15,y+15),fill=color,outline="#10232b",width=3)
        draw.text((x-38,y+20), label, fill=color,font=font(19,True))
    for block in spec["blocks"]:
        x,_,z=block["position"]
        sx,_,sz=block["size"]
        draw.rectangle(bounds(x,z,sx,sz),fill="#a0afb8",outline="#d9e0e3",width=2)
    for i,prop in enumerate(spec["placements"],1):
        x,_,z=prop["position"]
        if "collider_size" in prop:
            sx,_,sz=prop["collider_size"]
            angle=math.radians(prop["yaw_deg"])
            polygon=[]
            for a,b in ((-sx/2,-sz/2),(sx/2,-sz/2),(sx/2,sz/2),(-sx/2,sz/2)):
                polygon.append(pt(x+a*math.cos(angle)+b*math.sin(angle),z-a*math.sin(angle)+b*math.cos(angle)))
            draw.polygon(polygon,fill="#d2a65c",outline="#ffcf7d",width=2)
        else:
            px,py=pt(x,z)
            draw.ellipse((px-10,py-10,px+10,py+10),fill="#b69ae8")
        px,py=pt(x,z)
        draw.text((px-7,py-10),str(i), fill="#111e25", font=font(18,True))
    draw.rounded_rectangle((1023, 177, 1390, 938), radius=22, fill="#172934", outline="#3a5663", width=2)
    draw.text((1050,205), "LEVEL DATA", fill="#77d9c7",font=font(24,True))
    draw.text((1050,252),f"{width:g} m × {depth:g} m",fill="#e6eff4",font=font(30,True))
    draw.text((1050,302),f"{t['segments']} terrain subdivisions\n{len(spec['blocks'])} static cover elements\n{len(spec['placements'])} asset placements",
              fill="#b1c4cc",font=font(20),spacing=10)
    draw.text((1050,420),"ASSET PLACEMENTS",fill="#77d9c7",font=font(21,True))
    for i,prop in enumerate(spec["placements"],1):
        draw.text((1050,464+(i-1)*43),f"{i:02d}  {prop['id'].replace('_',' ')}",fill="#e6eff4",font=font(19))
    draw.text((1050,702),"LEGEND",fill="#77d9c7",font=font(21,True))
    for i,(label,col) in enumerate((("Static collision", "#a0afb8"),("Asset collider","#d2a65c"),("Unblocked mannequin","#b69ae8"),("Spawn-to-goal route","#78e0ac"))):
        y=750+i*36
        draw.rectangle((1050,y+3,1067,y+20),fill=col)
        draw.text((1078,y),label,fill="#b1c4cc",font=font(18))
    p0=pt(-width/2,depth/2); y=p0[1]+34
    draw.line([(p0[0],y),(p0[0]+5*scale,y)],fill="#e6eff4",width=4)
    draw.text((p0[0],y+8),"5 m",fill="#e6eff4",font=font(18))
    draw.text((1023,958),"Plan view · X horizontal · Z down",fill="#a3b7bf",font=font(17))
    image.save(output)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("--route",type=Path,help="Draw the planned route rather than a direct reference line")
    a=p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    render(json.loads(a.spec.read_text()), a.output, json.loads(a.route.read_text()) if a.route else None)
