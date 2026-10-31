"""Compile only the multi-turn helper against retained pinned P3.1 static libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path

DEFAULT=Path('<LOCAL_PATH_REMOVED>')


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,default=DEFAULT);args=p.parse_args()
    root=args.assets;build=root/'build';out=root/'p8';out.mkdir(exist_ok=True)
    source=Path(__file__).with_name('token_accounting.cpp')
    # Reuse generated compile/link settings, but never modify the prior build or binary.
    flags=(build/'CMakeFiles/padua-token-accounting.dir/flags.make').read_text().splitlines()
    options=[]
    for name in ['CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS']:
        options+=shlex.split(next(line.split('=',1)[1] for line in flags if line.startswith(name+' =')))
    link=shlex.split((build/'CMakeFiles/padua-token-accounting.dir/link.txt').read_text())
    executable=out/'padua-token-accounting';obj=out/'token_accounting.o'
    compiler=link[0]
    subprocess.run([compiler,*options,'-c',str(source),'-o',str(obj)],check=True)
    at=link.index('-o');link[at-1]=str(obj);link[at+1]=str(executable)
    subprocess.run(link,cwd=build,check=True)
    libraries={str((build/x).resolve()):hashlib.sha256((build/x).read_bytes()).hexdigest() for x in link if x.endswith('.a')}
    receipt={'llama_commit':'7170cad4d02f7907517613931840cbb2367399a3', 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'helper_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(), 'vocabulary_sha256':hashlib.sha256((root/'vocabulary-only.gguf').read_bytes()).hexdigest(),
             'static_libraries':libraries,'no_inference_or_service':True}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
