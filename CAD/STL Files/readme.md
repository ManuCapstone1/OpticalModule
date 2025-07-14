# 3D Printing Instructions

## Parts List
All .STL files to be 3D printed. Below is the list of all the parts and the quantity needed.
See [Download BOM.xlsx](./OpticalModule/Documentation/Github_BOM.xlsx) for a more detailed BOM.

| Part Name                | Notes                                | Quantity | Link |
|--------------------------|--------------------------------------|----------|------|
| *Enclosure Base V2       |                                      | 1        |      |
| Enclosure Cover Front    |                                      | 1        |      |
| Enclosure Cover Upper    |                                      | 1        |      |
| Belt Adapter             |                                      | 1        |      |
| Idler Mount B            |                                      | 1        |      |
| Idler Mount A            | Limit switch mount                   | 1        |      |
| **XY Motor mount         | One as is, the other mirrored.       | 2        |      |
| **Z Carriage             | One as is, the other mirrored.       | 2        |      |
| Ball Screw Bracket       |                                      | 1        |      |
| Belt Tensioner           |                                      | 1        |      |
| Z Motor bracket          |                                      | 1        |      |
| Left Y Carriage Top      |                                      | 1        | [rolohaun](https://github.com/rolohaun/SimpleCore/tree/main/CAD) | 
| Left Y Carriage Bottom   |                                      | 1        | [rolohaun](https://github.com/rolohaun/SimpleCore/tree/main/CAD) |
| Right Y Carriage Top     |                                      | 1        | [rolohaun](https://github.com/rolohaun/SimpleCore/tree/main/CAD) |
| Right Y Carriage Bottom  |                                      | 1        | [rolohaun](https://github.com/rolohaun/SimpleCore/tree/main/CAD) |
| X Limit Switch Mount     |                                      | 1        |       |
| Housing Top              |                                      | 1        |       |
| Housing Base             |                                      | 1        |       |
| estop enclosure top      |                                      | 1        |       |
| estop enclosure bottom   |                                      | 1        |       |
| Power supply housing     |                                      | 1        |       |
| Sample holder base       |                                      | 1        |       |
| Sample holder clamping plate |                                  | 2        |       |
| Sample holder pin        |   Add a spring from a pen to the cylindrical part of the pin.  | 2        |       |
| ***MGN9 Linear Rail Jig  |  Print standard/weaker settings.     | 2        | [Thingiverse](https://www.thingiverse.com/thing:5903898/files) |
| ***MGN12 Linear Rail Jig |  Print standard/weaker settings.     | 2        | [Thingiverse](https://www.thingiverse.com/thing:5903898/files) |
| T-bracket                |                                      | 4        | [Thingiverse](https://www.thingiverse.com/thing:2503622/files) |
| Top Corner Bracket       |                                      | 4        | [Thingiverse](https://www.thingiverse.com/thing:2655498) |
| Ball Screw Knob          | Scaled at 97%                        | 1        | [Thingiverse](https://www.thingiverse.com/thing:3014508/files) |
| Cable Management Clips   | File not uploaded. Select as needed. | ~10      | [Thingiverse](https://www.thingiverse.com/thing:4612080/files) |

**EnclosureBase should be printed with the supports filling in the interior of the shell.*

** *Print one as is, then print another but mirrored.*

*** *Since these parts are not apart of the ovedrall structure and used just for alignment, they can be printed on weak/low settings (e.g. infill 20%, shell thickness 0.8mm).*

## Recommended Print Settings
### Printer

Recommend using an *FDM printer*. Parts should hold good structural integrity to reduce wear and vibrations of the system.

### Material
Strong materials like ABS are the most preferred. However, PLA and PLA + are sufficient.

### Slicer Setting
The following suggestions are simply *suggestions*. If you are familiar with 3D printing, use you're discretion.

| Parameter        | Suggested Setting |
| -----------------| ----------------- |
| Resolution       | 0.02 mm           |
| Infill           | 40%-60%           |
| Infill Pattern   | Cubic             |
| Shell Thickness  | 1.2 mm            |
| Supports         | > 45 degrees. For nicer surface finish, place supports at the bottom of parts. |
