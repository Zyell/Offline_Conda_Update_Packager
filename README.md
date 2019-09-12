# Offline_Conda_Update_Packager
This script allows you to build an update of packages against a reference conda environment to be intalled in a duplicated offline environment.

This script was designed against and tested with Anaconda 2019.3 on both Windows 10 and Ubuntu 18.04.

Example usage is as follows:

```python

preamble = r'call C:\Users\username\Anaconda3\Scripts\activate.bat C:\Users\username\Anaconda3\envs\cool_environment'
generate_offline_install_package({'conda': ['pandas=0.25.1'], 'pip': ['pyarrow']}, compress=True,
                                 script_preamble=preamble)

```

The above will generate a batch file that can be used to activate and update an offline system on Windows.  Similarly, if run on Linux, this will generate a shell script.