from json.decoder import JSONDecodeError
import subprocess
import logging
from logging import debug, info, warning, error, critical, exception
import json
import os
import importlib
from argparse import ArgumentParser
import sys
from concurrent.futures import ThreadPoolExecutor
from git.repo.base import Repo

KEYS = ['name', 'entrypoint', 'appName']

def pip_install(name):
    conf = json.loads(os.environ['X_ICS_CONFIG'])
    proc = subprocess.Popen([conf['pipPath'], 'install', name, '--upgrade'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait()
    debug(f'Installed pip requirement {name}')

def load_project_folder(path):
    conf = json.loads(os.environ['X_ICS_CONFIG'])
    if os.path.exists(os.path.join(path, 'spec.json')):
        with open(os.path.join(path, 'spec.json'), 'r') as f:
            try:
                spec = json.load(f)
            except JSONDecodeError:
                error('Project spec in folder {path} contains invalid JSON. Skipping.')
                return
        debug(f'Loaded spec.json from {path}')
        try:
            if 'install' in spec.keys():
                debug(f'Project {spec["name"]} has installation steps. Proceeding.')
                if 'gitRemote' in spec['install'].keys(): # gitUrl, gitRepoPath
                    print(os.listdir(path))
                    if os.path.exists(os.path.join(path, spec['install']['gitRemote']['gitRepoPath'])):
                        debug('Repository already loaded, pulling from upstream...')
                        repo = Repo(os.path.join(path, spec['install']['gitRemote']['gitRepoPath']))
                        try:
                            repo.remote('origin')
                        except ValueError:
                            repo.create_remote('origin', spec['install']['gitRemote']['gitUrl'])
                        repo.remote('origin').pull()
                    else:
                        debug('Repository not yet pulled, cloning...')
                        os.makedirs(os.path.join(path, spec['install']['gitRemote']['gitRepoPath']), exist_ok=True)
                        repo = Repo.clone_from(spec['install']['gitRemote']['gitUrl'], os.path.join(path, spec['install']['gitRemote']['gitRepoPath']))
                        try:
                            repo.remote('origin')
                        except ValueError:
                            repo.create_remote('origin', spec['install']['gitRemote']['gitUrl'])
                    rootPath = os.path.join(path, spec['install']['gitRemote']['gitRepoPath'])
                    debug(f'Loaded git repository of project {spec["name"]}.')
                else:
                    rootPath = path + ''
                if 'requirements' in spec['install'].keys():
                    debug(f'Project {spec["name"]} has PIP requirements. Installing...')
                    if type(spec['install']['requirements']) == str:
                        try:
                            with open(os.path.join(rootPath, spec['install']['requirements']), 'r') as r:
                                reqs = r.read().split('\n')
                        except FileNotFoundError:
                            error(f'Could not find requirements file {spec["install"]["requirements"]} of project {spec["name"]}. Skipping.')
                            return
                    elif type(spec['install']['requirements']) == list:
                        reqs = spec['install']['requirements'][:]
                    else:
                        error(f'Invalid requirements entry in project {spec["name"]} (must be list or pathname). Skipping.')
                        return
                    
                    with ThreadPoolExecutor(max_workers=conf['workerPoolLimit']) as executor:
                        results = [executor.submit(pip_install, i) for i in reqs]
                    [r.result() for r in results]
                    debug(f'Installed all requirements of project {spec["name"]}')
                debug(f'Finished all installation steps of project {spec["name"]}.')
            debug(f'Checking keys of project {spec["name"]}...')
            for i in KEYS:
                spec[i]
            return path
        except KeyError:
            error(f'spec.json file of project at path {path} does not have all required keys. Skipping.')
    else:
        warning(f'Project folder {path} does not have a spec.json file.')
        

if __name__ == '__main__':
    parser = ArgumentParser(description='Run central server main process.')
    parser.add_argument('--config', default='config.json', help='Path to config file. Defaults to "config.json"')
    args = parser.parse_args()
    try:
        with open(args.config, 'r') as f:
            data = f.read()
            CONFIG = json.loads(data)
            os.environ['X_ICS_CONFIG'] = data
    except FileNotFoundError:
        print(f'ERROR: config file @ "{args.config}" not found.')
        sys.exit()
    except JSONDecodeError:
        print(f'ERROR: config file @ "{args.config}" contains invalid JSON.')
        sys.exit()
    
    logging.basicConfig(
        filename=CONFIG['logFile'],
        level=CONFIG['logLevel'],
        format=CONFIG['logFormat'],
        style='{'
    )
    info('Loaded config file.')

    if not os.path.exists(os.path.join(*CONFIG['projectRoot'].split('/'))):
        os.makedirs(os.path.join(*CONFIG['projectRoot'].split('/')))
        debug(f'Project root directory did not exist. Created directory {CONFIG["projectRoot"]}')
    
    info('Starting server, first-run.')
    while True:
        debug('Scanning project root for APIs.')
        with ThreadPoolExecutor(max_workers=CONFIG['workerPoolLimit']) as executor:
            pool = [executor.submit(load_project_folder, os.path.join(*CONFIG['projectRoot'].split('/'), p)) for p in os.listdir(os.path.join(*CONFIG['projectRoot'].split('/')))]
        
        all_results = [r.result() for r in pool]
        verified_paths = [i for i in all_results if i != None]
        os.environ['X_ICS_PATHS'] = json.dumps(verified_paths)
        info(f'Starting server with {str(len(verified_paths))} projects loaded.')
        input()