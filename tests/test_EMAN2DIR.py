from __future__ import print_function
import os
import EMAN2


files = [
    "fonts/DejaVuSerif.ttf", 
    "images/macimages/feather.png", 
    "images/macimages/EMAN2Icon.png", 
    "images/macimages/SirEMAN2.png",
    'lib/pmconfig/icons.json', 
    'lib/pmconfig/spr.json', 
    'lib/pmconfig/tomo.json', 
    'lib/pmconfig/tomosegpanel.json', 
]

eman2dir = os.getenv("EMAN2DIR")
print("EMAN2DIR: %s" % eman2dir)

for f in files:
    filepath = os.path.abspath(os.path.join(eman2dir, f))
    print("testing for existence of file via envar EMAN2DIR: %s" % filepath)
    
    assert os.path.isfile(filepath) == 1
