# 3D Printing Instructions

## Parts List
All .STL files to be 3D printed. Below is the list of all the parts and the quantity needed.
See [Download BOM.xlsx](./OpticalModule/BOM/BOM.xlsx) for a more detailed BOM.

| Part Name                 | Notes                     | Quantity | Link |
|---------------------------|---------------------------|----------|------|
| ***Enclosure Base V2.1    |                           | 1        |      |
| Enclosure Cover Front    |                           | 1        |      |
| Enclosure Cover Upper    |                           | 1        |      |
| Belt Adapter            |                           | 1        |      |
| Idler Mount B           |                           | 1        |      |
| Idler Mount A           | Limit switch mount        | 1        |      |
| *XY Motor mount          | Normal, Mirrored          | 2        |      |
| *Z carriage              | Normal, Mirrored          | 2        |      |
| Ball Screw Bracket      |                           | 1        |      |
| Z Motor bracket        |                           | 1        |      |
| Left Y carriage top    |                           | 1        | [rolohuan](https://github.com/rolohaun/SimpleCore/tree/main/CAD) | 
| Left Y carriage bottom |                           | 1        | [rolohuan](https://github.com/rolohaun/SimpleCore/tree/main/CAD)     |
| Right Y carriage top   |                           | 1        | [rolohuan](https://github.com/rolohaun/SimpleCore/tree/main/CAD)     |
| Right Y carriage bottom|                           | 1        | [rolohuan](https://github.com/rolohaun/SimpleCore/tree/main/CAD)     |
| X Limit Switch Mount   |                           | 1        |      |
| MGN9 Linear Rail Jig   |                           | 2        | [Thingiverse](https://www.thingiverse.com/thing:5903898/files) |
| MGN12 Linear Rail Jig  |                           | 2        | [Thingiverse](https://www.thingiverse.com/thing:5903898/files) |
| T-bracket             |                           | 4        | [Thingiverse](https://www.thingiverse.com/thing:2503622/files) |
| Top corner bracket    |                           | 4        | [Thingiverse](https://www.thingiverse.com/thing:2655498) |
| Belt tensioner        |                           | 1        |      |
| **Ball Screw Knob       |                           | 1        | [Thingiverse](https://www.thingiverse.com/thing:3014508/files) |

*Print one as is, then print another but mirrored.

**Print scaled at 99%.

## Recommended Print Settings
### Printer

Recommend using an *FDM printer*. Parts should hold good structural integrity to reduce wear and vibrations of the system.

### Material
Strong materials like ABS are the most preferred. However, PLA and PLA + are sufficient.

### Slicer Setting
The following suggestions are simply *suggestions*. If you are familiar with 3D printing, use you're discretion.

| Parameter  | Suggested Setting |
| ----------- | ----------------- |
| Resolution | 0.02 mm |
|  Infill | 40%-60% |
|  Infill Pattern | Cubic |
| Shell Thickness | 1.2 mm |
|  Supports | > 45 degrees. For nicer surface finish, place supports at the bottom of parts. |

*** EnclosureBase should be printed with the supports filling in the interior of the shell.
