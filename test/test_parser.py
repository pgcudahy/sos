#!/usr/bin/env python
#
# This file is part of Script of Scripts (SoS), a workflow system
# for the execution of commands and scripts in different languages.
# Please visit https://github.com/bpeng2000/SOS for more information.
#
# Copyright (C) 2016 Bo Peng (bpeng@mdanderson.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

# passing string as unicode to python 2 version of SoS
# to ensure compatibility
from __future__ import unicode_literals

import os
import unittest

from pysos import *

class TestParser(unittest.TestCase):
    def testFileFormat(self):
        '''Test recognizing the format of SoS script'''
        # file format must be 'fileformat=SOSx.x'
        self.assertRaises(ParsingError, SoS_Script,
            '#fileformat=SS2')
        self.assertRaises(ParsingError, SoS_Script,
            '#fileformat=SOS1.0beta')
        #
        # parse a larger script with gormat 1.1
        script = SoS_Script('scripts/section1.sos')
        # not the default value of 1.0
        self.assertEqual(script.format_version, '1.1')

    def testWorkflows(self):
        '''Test workflows defined in SoS script'''
        script = SoS_Script('''[0]''')
        self.assertEqual(sorted(script.workflows), ['default'])
        script = SoS_Script('''[0]\n[1]''')
        self.assertEqual(sorted(script.workflows), ['default'])
        script = SoS_Script('''[0]\n[*_1]''')
        self.assertEqual(sorted(script.workflows), ['default'])
        script = SoS_Script('''[0]\n[*_1]\n[auxillary]''')
        self.assertEqual(sorted(script.workflows), ['default'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]''')
        self.assertEqual(sorted(script.workflows), ['default', 'human'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]\n[mouse_2]''')
        self.assertEqual(sorted(script.workflows), ['default', 'human', 'mouse'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]\n[mouse_2]\n[s*_2]''')
        self.assertEqual(sorted(script.workflows), ['default', 'human', 'mouse'])

    def testSections(self):
        '''Test section definitions'''
        # bad names
        for badname in ['56_1', '_a', 'a_', '1x', '*', '?']:
            self.assertRaises(ParsingError, SoS_Script, '[{}]'.format(badname))
        # bad options
        for badoption in ['ss', 'skip a', 'skip:_', 'skip, skip']:
            self.assertRaises(ParsingError, SoS_Script, '[0:{}]'.format(badoption))
        # option value should be a valid python expression
        for badoption in ['sigil=a', 'input_alias=a']:
            self.assertRaises(ParsingError, SoS_Script, '[0:{}]'.format(badoption))
        # good options
        for goodoption in ['sigil="[ ]"', 'input_alias="a"']:
            SoS_Script('[0:{}]'.format(goodoption))
        # allowed names
        for name in ['a5', 'a_5', '*_0', 'a*1_100']:
            SoS_Script('[{}]'.format(name))
        # no directive in global section
        self.assertRaises(ParsingError, SoS_Script,
            '''input: 'filename' ''')
        # duplicate sections
        self.assertRaises(ParsingError, SoS_Script,
            '''[1]\n[1]''')
        self.assertRaises(ParsingError, SoS_Script,
            '''[1]\n[3]\n[2,1]''')
        self.assertRaises(ParsingError, SoS_Script,
            '''[a_1]\n[a_3]\n[*_1]''')
        # no duplicated section header
        SoS_Script('''[a_1]\n[a_3]\n[b*_1]''')

    def testGlobalVariables(self):
        '''Test definition of variables'''
        # global section cannot have directive
        self.assertRaises(ParsingError, SoS_Script,
            '''input: 'filename' ''')
        # or unrecognized directive
        self.assertRaises(ParsingError, SoS_Script,
            '''inputs: 'filename' ''')
        # or unrecoginzied varialbe
        self.assertRaises(ParsingError, SoS_Script,
            '''something ''')
        # or function call
        self.assertRaises(ParsingError, SoS_Script,
            '''somefunc() ''')
        # allow definition
        SoS_Script('''a = '1' ''')
        SoS_Script('''a = ['a', 'b'] ''')
        # but this one has incorrect syntax
        self.assertRaises(ParsingError, SoS_Script,
            '''a = 'b  ''')
        # This one also does not work because b is not defined.
        self.assertRaises(RuntimeError, SoS_Script,
            '''a = b  ''')
        # multi-line string literal
        SoS_Script('''a = """
this is a multi line
string """
''')
        # multi-line list literal, even with newline in between
        SoS_Script('''a = [
'a',

'b'
]
''')
        #
        script = SoS_Script('scripts/section1.sos')
        # not the default value of 1.0

    def testParameters(self):
        '''Test parameters section'''
        # directive not allowed in parameters
        self.assertRaises(ParsingError, SoS_Script,
            '''
[parameters]
input: 'filename' 
''')
        self.assertRaises(ParsingError, SoS_Script,
            '''
[parameters]
func()
''')    
        self.assertRaises(ArgumentError, SoS_Script,
            'scripts/section1.sos', args=['--not_exist'])
        self.assertRaises(ArgumentError, SoS_Script,
            'scripts/section1.sos', args=['--par1', 'a', 'b'])
        script = SoS_Script('scripts/section1.sos', args=['--par1', 'var2'])
        # need to check if par1 is set to correct value
        self.assertEqual(script.parameter('par1'), "var2")
        # 
        # test parameter using global definition
        script = SoS_Script('''
a="100"

[parameters]
b=str(int(a)+1)
''')
        self.assertEqual(script.parameter('b'), '101')
        script = SoS_Script('''
a=100

[parameters]
b=a+1
''')
        self.assertEqual(script.parameter('b'), 101)
        self.assertRaises(ArgumentError, SoS_Script, '''
a=100

[parameters]
b=a+1
''', args=['--b', 'a'])
        script = SoS_Script('''
a=100

[parameters]
b=a+1.
''', args=['--b', '1000'])
        self.assertEqual(script.parameter('b'), 1000)
        #
        # test string interpolation of the parameter section
        script = SoS_Script('''
a=100

[parameters]
b='${a+1}'
''')
        self.assertEqual(script.parameter('b'), '101')
        # test alternative sigil
        script = SoS_Script('''
a=100

[parameters: sigil='[ ]']
b='[a+1]'
''')
        self.assertEqual(script.parameter('b'), '101')




    def testSectionVariables(self):
        '''Test variables in sections'''
        # directive name cannot be used as variable
        self.assertRaises(ParsingError, SoS_Script,
            '''[0]
input='a.txt' ''')
        self.assertRaises(ParsingError, SoS_Script,
            '''[0]
output='a.txt' ''')
        self.assertRaises(ParsingError, SoS_Script,
            '''[0]
depends='a.txt' ''')

    def testSectionDirectives(self):
        '''Test directives of sections'''
        # cannot be in the global section
        self.assertRaises(ParsingError, SoS_Script,
            '''input: 'filename' ''')
        # multi-line OK
        SoS_Script('''
[0]
input: 'filename',
    'filename1'

''')
        # An abusive case with multi-line OK, from first column ok, blank line ok
        SoS_Script('''
[0]
input: 'filename',
'filename1',

filename4,
opt1=value
output: 
    blah

depends:
'something else'
''')
        # option with expression ok
        SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1

''')
        # unrecognized directive
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
something: 'filename',  filename2, opt=value==1
''')
        # need commma
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
input: 'filename'  filename2
''')
        # cannot be after action
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
func()        
input: 'filename',  'filename2', opt=value==1
''')
        # cannot be assigned between directives
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
input: 'filename',  'filename2', opt=value==1
a = 'some text'
output: 'filename',  'filename2', opt=value==1
''')
        # cannot be action between directives
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
input: 'filename',  'filename2', opt=value==1
abc
output: 'filename',  'filename2', opt=value==1
''')

    def testInput(self):
        '''Test input directive'''
        script = SoS_Script('''
[0]
files = ['a.txt', 'b.txt']

input: 'a.pdf', files, skip=False

''')
        script.workflow('default').run()

    def testSectionActions(self):
        '''Test actions of sections'''
        self.assertRaises(ParsingError, SoS_Script,
            '''func()''')
        SoS_Script(
            """
[0]
func('''
multiline 
string''', with_option=1
)
""")
        self.assertRaises(ParsingError, SoS_Script,
            '''
[0]
func(
''')

    def testDescriptions(self):
        '''Test script and workflow descriptions'''
        script = SoS_Script('''# first block

# global
# description

# human
# description of human

# description of human continued

[human_1]

a = '1'

# mouse
# mouse description
#

[mouse_1]
''')
        self.assertEqual(script.description, 'global\ndescription\n\n')
        self.assertEqual(script.workflow('human').description, 'description of human\ndescription of human continued\n')
        self.assertEqual(script.workflow('mouse').description, 'mouse description\n')

if __name__ == '__main__':
    unittest.main()
