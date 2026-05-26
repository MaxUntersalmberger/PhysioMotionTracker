#Deze GitHub is voor en door studenten :D

Installation: 
# Install/run from source code (i.e. the code in this repo)

Open an [Anaconda-enabled command prompt](https://www.anaconda.org) (or your preferred method of environment management) and enter the following commands:

1) Create a `Python` environment (Recommended version  is `python3.12`)

```bash
conda create -n HUmocap-env python=3.12
```

2) Activate that  environment

```bash
conda activate HUmocap-env
```

3) Clone the repository

```bash
git clone https://github.com/MaxUntersalmberger/PhysioMotionTracker
```

4) Install the library's

```bash
pip install -r "PhysioMotionTracker/Calibratie Programma/requirements.txt"
```

5) Launch the GUI (via the `guiMain.py` entry point)

```bash
python PhysioMotionTracker/GUI/guiMain.py
```

A GUI should pop up!

# How to use:

On the main page you can create a new project or open an existing project. 

## Selecting camera's
