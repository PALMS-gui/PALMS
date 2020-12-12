"""
Copyright (c) 2020 Stichting imec Nederland (https://www.imec-int.com/en/imec-the-netherlands)
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
# File mane
restart = 'Allows to restart the app to choose another database or file\r\n' \
          'Configuration settings from current session will be preserved'

restart_and_load_next = 'Restarts the app and automatically loads the next recording in the database list'

restart_and_load_prev = 'Restarts the app and automatically loads the prev recording'

# Track menu
remove_track = 'Delete currently selected view/track. The main track can not be deleted.\r\n' \
               'After deletion it is possible to recover the track by RightMouseClick in viewTable on the right\r\n' \
               'Still, alternative can be to make track invisible'

# Panel menu
add_panel = 'Create a new panel\r\n' \
            'Disabled, because multiple panels usage is implemented, but not bug-free\r\n' \
            'Creating panels, moving signals between them is possible, but annotation functionality might fail then.'

remove_panel = 'Close currently selected panel\r\n' \
               'Disabled, because multiple panels usage is implemented, but not bug-free\r\n' \
               'Creating panels, moving signals between them is possible, but annotation functionality might fail then.'

decresePanelSize = "Decrease the vertical size of the currently selected display panel"

increasePanelSize = "Increase the vertical size of the currently selected display panel"

syncronize = 'Syncronzation of signals between panels.\r\n' \
             'Disabled, because multiple panels usage is implemented, but not bug-free\r\n' \
             'Creating panels, moving signals between them is possible, but annotation functionality might fail then.'

toggleAll = "Hide/Show all tracks present in this panel except the main track"

# Annotation menu
annotationMode = '(fiducial_key) + LeftMouseClick: set annotation event\r\n RightMouseClick: delete nearest event'

partitionMode = 'CTRL + LeftMouseClick: create a partition\r\n' \
                'CTRL + RightMouseClick: delete a partition\r\n' \
                'SHIFT + LeftMouseDrag: move\expand partition'

epochMode = ''

browseMode = 'Read-only mode to scroll the data and see annotations\partitions\r\n' \
             'Activated when other modes are disabled'
annotation_config = 'GUI dialog that allows to see and modify\r\n' \
                    'some of the annotation settings from the loaded %annotationConfig.csv% file'

stickyFiducialMenu = 'Fix fiducial to avoid pressing keyboard button for each point'

partition_config = 'Placeholder for possible GUI partition configuration dialog as annotationConfigDialog'

annotationSave = 'Save annotations\partitions and (optionally) tracks into one .h5 file\r\n' \
                 'The filename will be the same as the original file.\r\n' \
                 'The output folder as set in the %databaseClass.output_folder (default: project root)'

annotationLoad = 'Load previously saved .h5 file with annotations and partitions'

# help menu
open_doc = 'Open user_manual.pdf in your browser\r\n'

# Other settings menu
autoscaleY = 'Make all signals scale Y axis to [min; max] of currently displayed chunk\r\n' \
             'Otherwise yrange stays constant [min;max] over the total signal'
showCursor = 'Toggle the display of the cursor position in the status bar'

save_tracks = 'When saving annotations\partitions, it is possible to save all tracks into .h5 file\r\n' \
              'These tracks are unmodified, as in the original file\r\n' \
              ' and can significantly increase the output file size'
save_overwrite = 'Checked: If an .h5 file with the same name exists, it is overwritten\r\n' \
                 'Unchecked: Another file with the current timestamp in its name is created'

# AnnotationConfigDialog
name = 'Fiducial name as set in annotationConfig file'
is_pinned = 'if DISABLED annotation is set on mouse click position\r\n' \
            'if ENABLED annotation might be adjusted based on other parameters'

pinned_to = 'Signal to be used as reference for annotation timestamp adjustment'
pinned_window = 'Window size to look for adjusted annotation timestamp\r\n' \
                'If no candidate is found, annotation timestamp is defined by initial mouse click'
spin_min_distance = 'How close in time two annotations can be\r\n' \
                    'If new annotation is located too close to an existing one,\r\n' \
                    ' a "duplicate annotation" message is given and no point added to the database'
key = 'Button to be pressed before LeftMouseClick to annotate not default fiducial\r\n' \
      'The default fiducial is the one on top of the list\r\n' \
      'If STICKY FIDUCIAL option is set, it is not necessary to press the button'
symbol = "One of: 'o','t','t1','t2','t3','s','p','h','+','star','d'"
symbol_colour = 'One of: r, g, b, c, m, y, k, w'
