"""Download official CPU runtime + Qwen GGUF. Executed by user during setup."""
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = 'qwen2.5-0.5b-instruct-q4_k_m.gguf'


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'UniversoLocal/0.1'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def download(url, destination, expected_sha=None):
    destination.parent.mkdir(exist_ok=True, parents=True)
    if destination.exists() and expected_sha:
        if hashlib.file_digest(destination.open('rb'), 'sha256').hexdigest() == expected_sha:
            print('Ja verificado:', destination.name)
            return
    temp = destination.with_suffix(destination.suffix+'.partial')
    req = urllib.request.Request(url, headers={'User-Agent':'UniversoLocal/0.1'})
    digest = hashlib.sha256()
    print('Baixando:', destination.name, flush=True)
    with urllib.request.urlopen(req, timeout=120) as response, temp.open('wb') as output:
        total=int(response.headers.get('Content-Length',0));count=0;last=-1
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            output.write(chunk);digest.update(chunk);count+=len(chunk)
            progress=int(count/total*100) if total else count//(1024*1024)
            if progress!=last:
                print(f'\r{progress}{"%" if total else " MB"}',end='',flush=True);last=progress
    print()
    if expected_sha and digest.hexdigest()!=expected_sha:
        temp.unlink(missing_ok=True)
        raise RuntimeError('Checksum incorreto: '+destination.name)
    temp.replace(destination)


def find_cpu_release():
    # /latest can point to a metadata-only stable release. CPU builds may
    # be prereleases, so inspect actual assets in the recent release list.
    for page in range(1, 4):
        releases = get_json(
            'https://api.github.com/repos/ggml-org/llama.cpp/releases'
            f'?per_page=20&page={page}'
        )
        for release in releases:
            if release.get('draft'):
                continue
            for asset in release.get('assets', []):
                if asset['name'].endswith('-bin-win-cpu-x64.zip'):
                    return release, asset
        if len(releases) < 20:
            break
    raise RuntimeError(
        'Pacote Windows CPU x64 nao encontrado nas versoes recentes. '
        'Consulte https://github.com/ggml-org/llama.cpp/releases'
    )


def main():
    if sys.platform!='win32':
        raise RuntimeError('Instalador de runtime destinado ao Windows x64. Consulte LEIA-ME.md para outros sistemas.')
    release, asset = find_cpu_release()
    print('Runtime selecionado:', release['tag_name'], asset['name'], flush=True)
    archive=ROOT/'runtime'/'llama-cpu.zip'
    sha=(asset.get('digest') or '').removeprefix('sha256:') or None
    download(asset['browser_download_url'],archive,sha)
    with zipfile.ZipFile(archive) as z:
        base=(ROOT/'runtime').resolve()
        for member in z.infolist():
            if not (base/member.filename).resolve().is_relative_to(base):
                raise RuntimeError('Caminho invalido no arquivo ZIP.')
        z.extractall(base)
    archive.unlink()
    metadata=get_json('https://huggingface.co/api/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF?blobs=true')
    info=next(x for x in metadata['siblings'] if x['rfilename']==MODEL)
    model_sha=info.get('lfs',{}).get('sha256')
    revision=metadata['sha']
    download(f'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{revision}/{MODEL}', ROOT/'models'/MODEL, model_sha)
    download(f'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{revision}/LICENSE',ROOT/'models'/'LICENSE-QWEN.txt')
    (ROOT/'runtime'/'versoes.json').write_text(json.dumps({'llama':release['tag_name'],'runtime_sha256':sha,'model_revision':revision,'model_sha256':model_sha},indent=2),encoding='utf-8')
    print('Pronto. Abra INICIAR_MODELO.bat e depois INICIAR_APP.bat.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('\nFalha:',exc)
        sys.exit(1)
