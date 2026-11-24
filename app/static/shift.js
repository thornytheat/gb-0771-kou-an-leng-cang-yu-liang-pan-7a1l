import {selectLot} from './tracks.js';
selectLot();
const dataset = document.querySelector('#dataset');
const status = document.querySelector('#status');
dataset.addEventListener('change', () => location.assign(`/view/${document.body.dataset.view}?sample=${dataset.value}`));
async function file(button, path, payload) {
  button.disabled = true;
  status.textContent = '复算中…';
  try {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message);
    status.textContent = result.reused ? '复算一致' : '归档完成';
    if (button.id === 'file-receipt') location.assign(`/view/history?${new URLSearchParams({receipt:result.id,sample:dataset.value})}`);
  } catch (error) {
    status.textContent = error.message || '请重试归档';
  } finally { button.disabled = false; }
}
document.querySelector('#docket').addEventListener('submit', event => {
  event.preventDefault(); file(event.submitter, '/api/receipts', {sample:dataset.value});
});
document.querySelector('#refresh')?.addEventListener('click', event => file(event.currentTarget, `/api/receipts/${event.currentTarget.dataset.id}/refresh`, null));

const booking = document.querySelector('#booking');
booking?.addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  const form = new FormData(event.currentTarget);
  const scope = booking.dataset.receipt ? {receipt:booking.dataset.receipt} : {sample:booking.dataset.sample};
  button.disabled = true;
  status.textContent = '登记预约…';
  try {
    const response = await fetch('/api/reservations', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...scope, order:form.get('order'), lot:form.get('lot'), slot:form.get('slot')})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message);
    status.textContent = `${result.reservation.order_ref} · ${result.status}${result.reused ? ' · 沿用原单' : ''}`;
    location.reload();
  } catch (error) {
    status.textContent = error.message || '预约未确认';
  } finally { button.disabled = false; }
});
