/* Untitled UI FREE portable DOM adapter, button and textField subset. MIT; see LICENSE.txt. */
(()=>{
function button(label, { color='primary', size='sm', disabled=false, loading=false, onPress, doc=document } = {}) {
  if (!['primary','secondary','tertiary','primary-destructive'].includes(color)) throw new Error('Unsupported button color');
  if (!['xs','sm','md','lg','xl'].includes(size)) throw new Error('Unsupported button size');
  const node = doc.createElement('button'); node.type = 'button'; node.className = 'uu-button'; node.dataset.color = color; node.dataset.size = size;
  const text = doc.createElement('span'); text.textContent = label; node.append(text);
  const update = ({disabled:nextDisabled=disabled, loading:nextLoading=loading}={}) => { disabled=nextDisabled; loading=nextLoading; node.disabled=disabled || loading; node.setAttribute('aria-busy',String(loading)); node.setAttribute('aria-label',label); };
  update();
  if (onPress) node.addEventListener('click', event => { if (!node.disabled) onPress(event); });
  node.setState = update;
  return node;
}
function textField(label, {id, hint='', value='', type='text', onInput, doc=document}={}) {
  if (!id) throw new Error('textField requires a stable unique id');
  const field=doc.createElement('div'); field.className='uu-field';
  const caption=doc.createElement('label'); caption.className='uu-label'; caption.htmlFor=id; caption.textContent=label;
  const input=doc.createElement('input'); input.className='uu-input'; input.id=id; input.type=type; input.value=value;
  const help=doc.createElement('p'); help.className='uu-hint'; help.id=id+'-hint'; help.textContent=hint; help.hidden=!hint; input.setAttribute('aria-describedby',help.id);
  field.append(caption,input,help);
  if(onInput) input.addEventListener('input',onInput);
  return { element:field,input,setError(message) { input.setAttribute('aria-invalid',String(Boolean(message))); help.textContent=message || hint; help.hidden=!(message || hint); help.classList.toggle('uu-error',Boolean(message)); } };
}

window.UNTITLED_UI=Object.freeze({button,textField});
})();
