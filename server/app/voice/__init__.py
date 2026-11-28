"""Voice commands and voice typing for IrisClick Desktop (panel revision).

commands.py    classifies spoken text: valid navigation, valid action, dictation or invalid
shortcuts.py   the sites and apps "Go to ..." may open (built-in list + the user's saved tiles)
typing.py      types dictated text into whatever text box has focus (Windows SendInput)
recognizer.py  offline Windows speech recognition (SAPI), English
controller.py  ties them together inside the tracking worker

The microphone is off until the user turns it on from the control bar; audio is
recognised on this computer and never stored or sent anywhere.
"""
