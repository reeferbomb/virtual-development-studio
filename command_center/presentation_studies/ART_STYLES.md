# Choosing a visual language

Start with one playable decision. At a flooded pumping station, the operator has to recognize the active signal and reach its platform. Draw the approach at its delivery size. Name the signal’s silhouette, the material that catches light, the color reserved for it and the detail the handheld version may lose. These choices give a second artist a brief they can actually apply.

## What the references demonstrate

- Epic describes how base color, metallic, roughness and specular inputs control surface response. Its examples distinguish a metal substrate from the paint covering it. A measured material reference can serve a stylized production as well as a realistic one. [Epic Games, *Physically Based Materials*](https://dev.epicgames.com/documentation/en-us/unreal-engine/physically-based-materials-in-unreal-engine)
- Valve’s rendering team describes coordinating character shapes with patterns of light and dark, hue variation and rim lighting. The goal was to help players read form under changing illumination while maintaining an illustrative style. [Mitchell, Francke and Eng, *Illustrative Rendering in Team Fortress 2*](https://cdn.akamai.steamstatic.com/apps/valve/2007/NPAR07_IllustrativeRenderingInTeamFortress2.pdf)
- Arc System Works technical artist Junya Christopher Motomura describes making a three-dimensional fighting game retain the visual character of its two-dimensional predecessors. The intended image guided both the art and the rendering work. [Motomura, *GuiltyGearXrd’s Art Style*, GDC 2015](https://www.gdcvault.com/play/1022031)
- Yacht Club Games describes choosing compact resolution and a limited palette for a handheld-inspired look, while departing from historical hardware constraints where appropriate. Its artists reserved more saturated colors for interactive objects. [Yacht Club Games, *The Art of the Game*](https://www.yachtclubgames.com/blog/the-art-of-the-game/)
- Godot’s GPU guide discusses geometry detail at distance, fill rate and the cost of transparency. The expensive part of a scene depends on what is visible and how it is drawn. Triangle counts and atlas sizes are useful planning figures, while frame time requires measurement on a device. [Godot Engine 4.5, *GPU optimization*](https://docs.godotengine.org/en/4.5/tutorials/performance/gpu_optimization.html)

## Ten directions for the pumping station

These are studio applications of the sources. Each row proposes a treatment of the same scene and a way to inspect it. Industrial design can supply the setting, horror can supply the mood, and several rendering styles can support either.

| Direction | Art and camera choices | Check at gameplay distance |
| --- | --- | --- |
| Photorealistic | Use measured proportions, plausible metal and paint response, and light from identifiable fixtures. Put wear where operators touch the rail. | Compare the signal under daylight and work lamps. Look for baked-in highlights that stay fixed when the light moves. |
| Semi-realistic | Keep believable construction and light response, simplify small fittings, and enlarge the signal housing slightly. | See whether the exaggerated housing still mounts and operates believably in close-up. |
| Stylized | Repeat broad wedges and soft corners. Reserve one angular silhouette for the signal head. | Black out the textures and ask a player to find the head amongst the other fixtures. |
| Painterly | Group the machinery into broad values. Concentrate sharp brushwork around the platform entrance; soften distant pipes. | Pan at normal speed and inspect whether fine strokes flicker or overwhelm the turn. |
| Cel-shaded | Choose the number and spacing of light bands. Design the signal’s profile around a shadow shape that survives a camera turn. | Orbit the prop. Watch the shadow boundary and outline where the housing crosses a rail. |
| Low-poly | Spend facets on the housing’s outer contour. Give broad supporting planes a shared normal and remove hidden detail first. | Switch detail levels at the approach distance and check whether the silhouette changes meaning. |
| Pixel art | Work on an explicit pixel grid, cluster highlights and choose a scaling treatment. Give the signal and its shadow distinct contiguous shapes. | Walk one screen pixel at a time and inspect uneven pixel widths, broken contours and camera shimmer. |
| Retro | Choose a particular historical vocabulary, such as a small palette and chunky perspective geometry. Document which constraints the project borrows. | Test HUD scale and input legibility on the current display, including the effects-on and effects-off views. |
| Industrial | Give pipes a destination, allow space to service machinery and vary bolted, cast and welded surfaces by function. Reserve safety markings for operational cues. | Follow the route from intake to platform. Can a player tell a load-bearing truss from the switch assembly? |
| Horror | Stage alternating visibility, occlusion and pools of motivated light. Give the route one stable landmark while surrounding details can remain uncertain. | Approach at supported brightness and contrast settings. Ask players what they can operate and where they can retreat. |

## Test the tradeoff

For the station exercise, the signal sits right of center above two material groups. Compare an indexed thumbnail of the full kit with its handheld revision at the same framing. Count shared silhouette cells and measure edge contrast under both declared light conditions. Keep the smoother signal finish distinct from the wall. Account for triangles across every placed instance, count one shared atlas per tier, and reduce both costs before reporting the result. [Art-styles exercise](../lab_art_styles.py)

In a build, capture the same approach on the target display using representative motion and HUD settings. Check the landmark while turning, inspect specular flicker and outline stability, and profile CPU time, GPU time and texture residency. The thumbnail exercise omits these effects.
