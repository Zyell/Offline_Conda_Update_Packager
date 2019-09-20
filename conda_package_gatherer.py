import conda.cli.python_api as conda
from conda.core.solve import Solver, IndexedSet
from conda.models.match_spec import MatchSpec
from typing import List, Dict, Union, Optional, Tuple
import json
import os
import yaml
from concurrent.futures import ThreadPoolExecutor
import requests
import logging
import shutil
import subprocess
import sys


logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logging.INFO)


def download_and_save_package(url: str, package_name: str,
                              download_directory: str) -> None:
    """

    download the conda package and save it to a specified directory

    :param url: url with the conda package
    :param package_name: conda package name
    :param download_directory: the directory to save packages to
    :return: None
    """
    logging.info(f'fetching {package_name} from {url}')
    data = requests.get(url)
    file = data.content
    with open(os.path.join(download_directory, package_name), 'wb') as pkg:
        pkg.write(file)
    logging.info(f'package {package_name} saved to {download_directory}')


def fetch_packages(urls: Dict[str, str], download_directory: Optional[str]) -> None:
    """

    fetch all conda packages asynchronously, limiting the number fetched at one time using a semaphore

    :param urls: diction or urls and package names to fetch
    :param download_directory: the directory to save packages to
    :return: None
    """
    with ThreadPoolExecutor(max_workers=10) as executor:
        for u, p in urls.items():
            executor.submit(download_and_save_package, u, p, download_directory)


def solve_for_packages(packages: List[str]) -> Tuple[IndexedSet, IndexedSet]:
    """

    given a list of conda packages solve the environment for dependencies

    :param packages: list of conda packages to be installed
    :return: tuple of packages that will be removed and will be added to the current conda environment
    """
    specs_to_add = [MatchSpec(p) for p in packages]
    info = json.loads(conda.run_command(conda.Commands.INFO, '--json')[0])
    prefix = info['conda_prefix'] if info['active_prefix'] == 'null' else info['active_prefix']
    solver = Solver(prefix, info['channels'], specs_to_add=specs_to_add)
    return solver.solve_for_diff()


def generate_offline_install_package(packages: Union[Dict[str, List], str], package_location: Optional[str] = '.',
                                     install_package_name: Optional[str] = 'package',
                                     compress: Optional[bool] = False,
                                     exist_ok: Optional[bool] = True,
                                     script_preamble: Optional[str] = None) -> None:
    """

    gathers all packages necessary for offline installation given a list of conda and pip installable packages or a
    conda environment file and builds executable batch file or shell script for their offline installation

    :param packages: dictionary of conda and pip packages that need to be installed
    :param package_location: location to gather packages
    :param install_package_name: name of folder or zipped resultant offline install package
    :param compress: boolean to indicate of the resultant folder should be compressed
    :param exist_ok: passed to os.makedirs to either continue if directory exists or raise an error
    :param script_preamble: a string that is passed to do something before installing packages,
        for instance, activating a particular environment
    :return: None
    """
    if isinstance(packages, str):
        # we assume this is the location of an environment.yaml file
        with open(packages) as pkgs:
            data = yaml.safe_load(pkgs)
        packages = data['dependencies']
        pip_dependencies = None
        for p in reversed(packages):
            if isinstance(p, dict) and p.get('pip') is not None:
                pip_dependencies = p.pop('pip')
                packages.remove(p)
                break
        conda_dependencies = packages
    else:
        conda_dependencies = packages.get('conda')
        pip_dependencies = packages.get('pip')
    install_path = os.path.join(os.path.abspath(package_location), install_package_name)
    os.makedirs(install_path, exist_ok=exist_ok)
    conda_package_listing = None
    if conda_dependencies is not None:
        conda_packages_location = os.path.join(install_path, 'conda')
        os.makedirs(conda_packages_location, exist_ok=exist_ok)
        _, to_be_installed = solve_for_packages(conda_dependencies)
        packages_to_fetch = {pkg.url: pkg.fn for pkg in to_be_installed.item_list}
        conda_package_listing = [f'conda/{v}' for v in packages_to_fetch.values()]
        logging.info(f'need the following conda packages: {packages_to_fetch}')
        fetch_packages(packages_to_fetch, download_directory=conda_packages_location)
    if pip_dependencies:
        pip_packages_location = os.path.join(install_path, 'pip')
        os.makedirs(pip_packages_location, exist_ok=exist_ok)
        subprocess.check_call([sys.executable, '-m', 'pip', 'download', *pip_dependencies,
                               '-d', os.path.join(pip_packages_location, 'downloaded')])
        with open(os.path.join(pip_packages_location, 'requirements.txt'), 'w') as rq:
            for p in pip_dependencies:
                rq.write(p)
    if os.name == 'nt':
        update_file = 'update.bat'
        comment_mark = '::'
        file_mark = ""
        command_prepend = 'call '
    else:
        update_file = 'update.sh'
        comment_mark = '#'
        file_mark = '#!/bin/bash\n'
        command_prepend = ''
    with open(os.path.join(install_path, update_file), 'w') as up:
        up.write(file_mark)
        if script_preamble is not None:
            up.write(script_preamble)
            up.write('\n')
        if conda_package_listing is not None:
            up.write(f'{comment_mark} install conda packages\n')
            up.write(f'{command_prepend}conda install {" ".join(conda_package_listing)} --offline\n')
        if pip_dependencies is not None:
            up.write(f'{comment_mark} install pip packages\n')
            up.write(f'{command_prepend}pip install --no-index --find-links=pip/downloaded -r pip/requirements.txt\n')
    if compress:
        shutil.make_archive(install_path, 'zip', install_path)
