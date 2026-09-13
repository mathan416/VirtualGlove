# Project: VirtualGlove
# File: tests/test_matrix_renderer.py
# Purpose: Execute the firmware renderer to verify idle brightness and protected modes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-06 - Implement approved player and connectivity refinements.
#   2026-09-06 - Check idle-only brightness and sparse connection pixels in actual C++.

"""Exercise firmware framebuffers using a host-side matrix sink."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PREFIX = '#include <cstdint>\n#include <cstring>\n#include <cassert>\n#include <string>\n#include <algorithm>\nusing String=std::string;\n#define VIRTUALGLOVE_FIRMWARE_ID "test"\nstruct Arduino_LED_Matrix { uint8_t frame[104]={}; void draw(uint8_t* p){std::memcpy(frame,p,104);} void clear(){std::memset(frame,0,104);} };\nstruct k_thread {};\nusing k_thread_stack_t=int;\nusing k_tid_t=void*;\nunsigned long fakeTime=10000;\nunsigned long millis(){return fakeTime;}\n'
MAIN = '\nint main(){\n for(int n=0;n<29;n++){drawIdleFrame(n);uint8_t full[104];std::memcpy(full,matrix.frame,104);drawIdleFrame(n,2);for(int i=0;i<104;i++){assert(matrix.frame[i]<=2);assert((full[i]==0)==(matrix.frame[i]==0));}}\n for(int state=0;state<=8;state++){\n  requestedStatus=state;requestedProfile=11;drawnStatus=-1;requestedAttract=0;refreshMatrix();uint8_t reference[104];std::memcpy(reference,matrix.frame,104);\n  if(state!=PG_GESTURES_IDLE){for(int mode=1;mode<=2;mode++){drawnStatus=-1;set_virtualglove_attract(mode,7);refreshMatrix();assert(std::memcmp(reference,matrix.frame,104)==0);}}\n }\n requestedStatus=PG_GESTURES_IDLE;drawnStatus=-1;set_virtualglove_attract(2,7);refreshMatrix();for(int i=0;i<104;i++)assert(matrix.frame[i]==(i==91||i==93||i==95||i==97?1:0));\n set_virtualglove_attract(2,0);refreshMatrix();assert(matrix.frame[91]==1&&matrix.frame[93]==0&&matrix.frame[95]==0&&matrix.frame[97]==0);\n}\n'
NUMERIC_CHECK = '\n drawProfile(12,false);uint8_t one[104];std::memcpy(one,matrix.frame,104);int oneLit=0;for(int i=0;i<104;i++)oneLit+=one[i]>0;assert(oneLit>0);\n drawProfile(25,false);int fourteenLit=0;for(int i=0;i<104;i++)fourteenLit+=matrix.frame[i]>0;assert(fourteenLit>oneLit);assert(std::memcmp(one,matrix.frame,104)!=0);\n set_virtualglove_profile(25);assert(requestedProfile==25);set_virtualglove_profile(26);assert(requestedProfile==0);\n'

class MatrixRendererTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "C++ compiler required for firmware renderer")
    def test_idle_brightness_and_protected_displays(self):
        source = (Path(__file__).resolve().parents[1]/"sketch/sketch.ino").read_text()
        body = source[source.index("enum PowerGloveStatus"):source.index("// Keep the display alive")]
        body += source[source.index("void refreshMatrix() {"):source.index("// Fall back to loop-driven")]
        with tempfile.TemporaryDirectory() as directory:
            cpp, binary = Path(directory)/"renderer.cpp", Path(directory)/"renderer"
            cpp.write_text(PREFIX+body+MAIN.replace("\n}\n", NUMERIC_CHECK+"\n}\n"))
            subprocess.run(["c++","-std=c++11",str(cpp),"-o",str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
