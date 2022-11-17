#!/usr/bin/env python3
import aiohttp
import aiofiles
import mimetypes
from tqdm import tqdm
#from http.server import BaseHTTPRequestHandler, HTTPServer
import time, sys, logging, os, json, mimetypes
from pathlib import Path
import argparse
import itertools
import asyncio

### init paths and homedir
home=Path.home() / '.swarmsync'
ALLFILES=Path.home() / '.swarmsync/allfiles.json'
TODO=Path.home() / '.swarmsync/todo.json'
RESPONSES=Path.home() / '.swarmsync/responses.json'
Path(home).mkdir(exist_ok=True)

def append_list(file, a_list):
    with open(file, "a") as fp:
        json.dump(a_list, fp)

def write_list(file, a_list):
    with open(file, "w") as fp:
        json.dump(a_list, fp)

def write_dict(file, a_dict):
    with open(file, "w") as f:
        f.write(str(a_dict))

# Read list to memory
def read_list(file):
    try:
        with open(file, 'r') as fp:
            n_list = json.loads(fp)
            return n_list
    except OSError:
        return None

def read_dict(file):
    try:
        with open(file, 'r') as fp:
            n_list = json.load(fp)
            return n_list
    except OSError:
        return None

class Object:
    def toJSON(self):
        return json.dump(self, default=lambda o: o.__dict__,
            sort_keys=True, indent=4)

def prepare():
  global url,pin,stamp
  url=args.beeurl
  pin=args.pin
  stamp=args.stamp
  yes = {'yes','y', 'ye', ''}
  no = {'no','n'}

  FILES=sorted(list(filter(lambda x: x.is_file(), Path(args.path).rglob(args.search))))
  jsonList = []
  for f in FILES:
      jsonList.append({ "file": str(os.fspath(f))})
  
  if Path(ALLFILES).is_file():
    oldList = read_dict(ALLFILES)
    if jsonList != oldList:
      print('New files list differs from the old..')
      choice = input('Do you want to overwrite list and todo ? [Y]es/[n]o:').lower()
      if choice in yes:
        write_list(ALLFILES, jsonList)
        write_list(TODO, jsonList)
  else:
    write_list(ALLFILES, jsonList)
    print("same files. lets continue...\n")
  
  if Path(TODO).is_file():
    todo = read_dict(TODO)
    print ('todo exists. lets continue...')
  else:
    write_list(TODO, jsonList)

class FileManager():
    def __init__(self, file_name: str):
        self.name = file_name
        self.size = os.path.getsize(self.name)
        self.pbar = None

    def __init_pbar(self):
        self.pbar = tqdm(
            total=self.size,
            desc=self.name,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            colour='#ff8c00',
            leave=True)

    async def file_reader(self):
        self.__init_pbar()
        chunk_size = 64*1024
        async with aiofiles.open(self.name, 'rb') as f:
            chunk = await f.read(chunk_size)
            while chunk:
                self.pbar.update(chunk_size)
                yield chunk
                chunk = await f.read(chunk_size)
            self.pbar.close()

def response_dict(a_dict):
  l_dict = [a_dict]
  o_dict = read_dict(RESPONSES)
  if o_dict is not None:
    o_dict.append(a_dict)
    write_dict(RESPONSES, str(o_dict).replace("'",'"'))
  else:
    write_dict(RESPONSES, str(l_dict).replace("'",'"'))

async def aioupload(file: FileManager, url: str, session: aiohttp.ClientSession, sem):
    resp_dict = []
    (MIME,_ )=mimetypes.guess_type(file.name, strict=False)
    headers={"Content-Type": MIME, "swarm-deferred-upload": "false", "swarm-pin": pin,
            "swarm-postage-batch-id": stamp }
    try:
        async with sem, session.post(url + '?name=' + os.path.basename(file.name),
                                headers=headers, data=file.file_reader()) as res:
            scheduled.remove(file.name)
            if 200 <= res.status <= 300:
              response = await res.json()
              ref = response['reference']
              resp_dict = { "item": [ { "file": file.name, "reference": ref, } ] }
            #else:
              #print(res.status)
            response_dict(resp_dict)
            # if we have a reference we can asume upload was sucess
            # so remove from todo list
            if len(ref) == 64:
              todo.remove({"file": file.name })
              write_list(TODO, todo)
            return res
    except Exception as e:
        # handle error(s) according to your needs
        print(e)
    finally:
        sem.release()

async def async_upload(scheduled):
    scheduled = [FileManager(file) for file in scheduled]
    sem = asyncio.Semaphore(args.count)
    async with sem, aiohttp.ClientSession() as session:
        res = await asyncio.gather(*[aioupload(file, url, session, sem) for file in scheduled])
    print(f'items uploaded ({len(res)})')


def cleanup(file):
  #sanitze responses if there was a failure
  clean = read_dict(file)
  if clean is not None:
    clean = str_list = list(filter(None, clean))
    write_dict(file, str(clean).replace("'",'"'))

def main():
  global scheduled
  cleanup(RESPONSES)
  todo = read_dict(TODO)
  listlen=len(todo)
  print('\n\n\n')
  scheduled=[]
  for x in todo:
    scheduled.append(x['file'])
  asyncio.run(async_upload(scheduled))
  cleanup(RESPONSES)

def upload():
  if args.path:
      print ("path: ", args.path)
  if args.count:
      print ("count: ", args.count)
  if args.search:
      print ("search: ", args.search)
  if args.stamp:
      print ("stamp: ", args.stamp)
  if args.pin:
      print ("pin: ", args.pin)
  if args.beeurl:
  #    args.beeurl = os.path.join(args.beeurl, '')
      print ("url: ", args.beeurl)
  prepare()
  main()

def show():
  if 'todo' in args.s:
    get = read_dict(TODO)
    print(json.dumps(get, indent=4))
  if 'responses' in args.s:
    get = read_dict(RESPONSES)
    print(json.dumps(get, indent=4))

#if __name__ == "__main__":
    #sys.exit(main())

# Initialize parser
parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers()
parser_upload = subparsers.add_parser('upload', help='upload help')
parser_show = subparsers.add_parser('show', help='show help')
parser_show.add_argument('s', type=str, help = """enter string what to show.
                         options: todo, responses""", choices=['todo', 'responses'],
                         metavar='<name_of_list>', default='responses')
parser_show.set_defaults(func=show)
# Adding optional argument
parser_upload.add_argument("-p", "--path",type=str, help = "path to upload", default=".")
parser_upload.add_argument("-u", "--beeurl", type=str, help = "beeurl", default="http://0:1633/bzz")
parser_upload.add_argument("-c", "--count", type=int, help = "number of concurrent uploads", default=5)
parser_upload.add_argument("-s", "--search", type=str, help = "search param(* or *.jpg or somename.txt", default="*.*")
parser_upload.add_argument("-S", "--stamp", type=str, help = "bee batch", default="57819a5ac47d3a8bd4a9817c23a40e2105e27fcb9c1073e53a490a562879e0c9")
parser_upload.add_argument("-P", "--pin", type=str, help = "pin", default="False")
parser_upload.set_defaults(func=upload)

if len(sys.argv)==1:
  parser.print_help(sys.stderr)
  sys.exit(1)

args = parser.parse_args()
if args.func:
    args.func()

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

