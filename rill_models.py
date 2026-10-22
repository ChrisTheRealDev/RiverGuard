"""Bounded Ollama metadata and preloading; never pulls or executes a model name."""
import re
import asyncio
from urllib.parse import urlsplit

import httpx
import rill_ai


def local_server():
    return rill_ai.provider()=='ollama' and rill_ai.provider_info()['local']


def _local_entry(value):
    name=value.get('name') or value.get('model') or ''
    return (bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}',name))
            and not value.get('remote_host') and not value.get('remote_model')
            and not re.search(r'(?:[:/-])cloud(?:$|[:/-])',name,re.I))


def destination():
    url=urlsplit(rill_ai.HOST)
    host=url.hostname or ''
    if ':' in host:host='['+host+']'
    return f'{url.scheme}://{host}'+(f':{url.port}' if url.port else '')


async def validate_local_model(model, client):
    """Recheck aliases immediately before sending any question or sensor data."""
    if not local_server() or not _local_entry({'name':model}):
        raise rill_ai.RillError('This model cannot be used as local AI. Select an installed local model in Settings.')
    try:
        response=await client.post(rill_ai.HOST+'/api/show',json={'model':model},timeout=5)
        if not response.is_success:
            raise rill_ai._local_error('',response.status_code,model)
        details=response.json()
        if (details.get('remote_host') or details.get('remote_model')
                or 'completion' not in details.get('capabilities',[])):
            raise rill_ai.RillError('The selected model is not a local chat model. No question or readings were sent. Choose a local model in Settings.')
    except (httpx.HTTPError,ValueError,TypeError,AttributeError) as exc:
        raise rill_ai.RillError('Could not verify the local model. Start Ollama, then retry. Your question and readings were not sent.') from exc


async def catalog(client=None):
    try:
        return await asyncio.wait_for(_catalog(client),15)
    except TimeoutError as exc:
        raise rill_ai.RillError('Ollama took too long to list models. Try Refresh models again.') from exc


async def _catalog(client=None):
    if not local_server():
        raise rill_ai.RillError('Model selection requires local Ollama on this laptop. The configured provider has not been changed.')
    own=client is None
    if own:client=httpx.AsyncClient(timeout=httpx.Timeout(8,connect=2),trust_env=False)
    try:
        response=await client.get(rill_ai.HOST+'/api/tags')
        response.raise_for_status()
        entries=response.json().get('models',[])
        models=[]
        for entry in entries[:50]:
            if not _local_entry(entry):continue
            name=entry.get('name') or entry.get('model')
            # Tags alone are insufficient: a locally named alias can proxy cloud.
            shown=await client.post(rill_ai.HOST+'/api/show',json={'model':name})
            shown.raise_for_status()
            details=shown.json()
            if (details.get('remote_host') or details.get('remote_model')
                    or 'completion' not in details.get('capabilities',[])):
                continue
            info=details.get('details',{})
            models.append(dict(name=name,size=entry.get('size',0),
                               parameter_size=info.get('parameter_size',''),
                               quantization_level=info.get('quantization_level',''),
                               thinking='thinking' in details.get('capabilities',[])))
        loaded=[]
        try:
            response=await client.get(rill_ai.HOST+'/api/ps')
            response.raise_for_status()
            for entry in response.json().get('models',[]):
                if not _local_entry(entry):continue
                vram=entry.get('size_vram',0) or 0
                running=dict(name=entry.get('name') or entry.get('model'),
                             processor='CPU' if not vram else 'GPU' if vram>=entry.get('size',0) else 'CPU + GPU')
                if 'context_length' in entry:running['context_length']=entry['context_length']
                loaded.append(running)
        except (httpx.HTTPError,ValueError,TypeError):
            pass  # Installed models remain selectable when running-status is unavailable.
        return {'models':models,'loaded':loaded}
    except (httpx.HTTPError,ValueError,TypeError,AttributeError) as exc:
        raise rill_ai.RillError('Could not list local models. Start Ollama, then refresh the model list. Your current model is unchanged.') from exc
    finally:
        if own:await client.aclose()


async def preload(model,client=None):
    own=client is None
    if own:client=httpx.AsyncClient(timeout=httpx.Timeout(60,connect=3),trust_env=False)
    try:
        response=await client.post(rill_ai.HOST+'/api/chat',json={
            'model':model,'messages':[],'stream':False,'keep_alive':'15m',
            'options':{'num_ctx':4096,'num_predict':256}})
        if not response.is_success:
            raise rill_ai._local_error('',response.status_code,model)
        if response.json().get('done') is not True:
            raise rill_ai.RillError('Ollama did not finish preparing the model. Retry Prepare model when it is ready.')
    except (httpx.HTTPError,ValueError) as exc:
        raise rill_ai.RillError('Could not prepare the local model. Start Ollama and check available memory, then try again. Saved chats are unchanged.') from exc
    finally:
        if own:await client.aclose()
