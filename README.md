# PALMS
Platform for Analysis and Labeling of Medical Time Series  
This software features the following pubication: 
https://www.mdpi.com/1424-8220/20/24/7302/htm

##### Fiducials annotation: https://vimeo.com/490142964    
![Fiducials annotation](https://i.ibb.co/qyJfgK5/FIG3.png)  
##### Partitions annotation: https://vimeo.com/490143050   
![Partitions annotation](https://i.ibb.co/tcjGtyr/FIG4.png)  
##### Quality annotation  
![Quality annotation](https://i.ibb.co/TT66Ydr/FIG5.png)

# LICENSE
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)  
https://www.imec-int.com/en/imec-the-netherlands  
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>  
See COPYING, README.  

# ATTRIBUTION
This software includes (modified) third party open source software components distributed under the MIT license:  
./gui/display_panel.py,  
./gui/model.py,  
./gui/plot_area.py,  
./gui/rendering.py,  
./gui/tracking.py,  
./gui/view_table.py,  
./gui/viewer.py    
For license text see ./gui/LICENSE.txt

This software includes (modified) third party open source software components distributed under the MIT license:   
./utils/QRSDetectorOffline.py  
See license in the source code.

This software makes use of the GPL-3.0+ licensed PyQt library (Riverbank Computing Limited).  
For more info see https://www.riverbankcomputing.com/static/Docs/PyQt5/ 

The two example data files (see __Examples__ below) contain raw data from:
- IEEE TBME Respiratory Rate Benchmark data set: http://www.capnobase.org/database/pulse-oximeter-ieee-tbme-benchmark/ 
- BIDMC PPG and Respiration Dataset: https://physionet.org/content/bidmc/1.0.0/

# HOW TO START USING THE TOOL
A) Using source code:  
1.1 Install Python 3.6 from https://www.python.org/ftp/python/3.6.8/python-3.6.8-amd64.exe as Admin and add Python to the PATH  
1.2 (advised) create a separate virtual environment in the root folder of the project: https://www.jetbrains.com/help/pycharm/creating-virtual-environment.html    
1.3 Install required packages: *pip install -r requirements.txt*  
1.4 Run the tool: *python \_\_main\_\_.py*  

B) Using portable (executable) version:  
1.1 PALMS.exe and required dependencies for portable execution of the software is available in *!portable\\*     
  
  
2. A pop-up window with available databases will appear (see also __Examples__ below)  
3. Select a database and a file to annotate   

# EXAMPLES
PALMS is provided with 2 ready-to-run examples for annotating:  
- PPG peak and foot (see *logic\databases\EXAMPLE_PPG.py*)
- respiration signal fiducials (see *logic\databases\EXAMPLE_RESPIRATION.py*)		

Small data chunks for these examples to work are stored in *docs\examples\\*   

PALMS also provides a configuration file *logic\databases\ECG_Physionet2011.py* 
to make possible ECG quality annotation of Physionet data. In order to run this example
one has to download some datafiles from the corresponding Physionet database and place them 
into *docs\examples\examples_Physionet2011\\*

# DOCUMENTATION
User_manual (may be outdated): *docs\user_manual.pdf*    
Demo video (may be outdated):
1. Browse: https://vimeo.com/490143111  
2. Annotation: https://vimeo.com/490142964  
3. Partitions: https://vimeo.com/490143050 


Instructions for creating new database-configurations: *logic\\databases\\EXAMPLE_...*   


# HOW TO CREATE AN EXECUTABLE VERSION OF THE TOOL
Portable version allows someone without even Python installed to use the software.

1. Execute in the console: *pyinstaller --onefile --name PALMS __main__.py*
2. Modify *PALMS.spec* created in the root to add non-python files necessary to run the app:  
2.1 Add the following block of code:  
  ...  
  added_files = [  
    ("docs\\examples", "docs\\examples" ),  
    ("docs\\user_manual.pdf","docs"),  
    ("gui\\LICENSE.txt", "gui"),  
    ("config\\shortcuts.json","config"),  
    ("config\\icons\\PALMS.png","config\\icons"),  
    ("config\\AnnotationConfig","config\\AnnotationConfig"),  
    ("config\\EpochConfig","config\\EpochConfig"),  
    ("logic\\databases\\EXAMPLE_PPG.py","logic\\databases"),  
    ("logic\\databases\\EXAMPLE_RESPIRATION.py","logic\\databases")  
    ]  
  ...    
2.2 Below find a line 'datas=[],' and assign:  
  datas = added_files  
  ...

2.3 including ("config\\shortcuts.json","config") will make shortcuts fixed, won't be possible to change in portable version.
Omitting this will require a config\shortcuts.json to be near executable when running (or default is used)  
3. Execute in the console: *pyinstaller --onefile PALMS.spec*  
4. PALMS.exe is ready in *dist\\*  
5. In order PALMS.exe to work and find all necessary files it should be given to an annotator-expert in the following folder with accordingly configured newDatabase.py.
(PALMS.exe will contain all necessary dependencies to show examples) 

annotation_task\  
  |-- data_folder\  
    |-- file_to_annotate  
  |-- PALMS.exe  
  |-- newDatabase.py (contains newDatabase class, see EXAMPLES)  
  |-- config.json  
