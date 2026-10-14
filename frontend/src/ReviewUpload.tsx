import {useState} from 'react';
import {ArrowRight, FileCheck2, FileText, Play, Upload} from 'lucide-react';
import {Field} from './ui';
import {disciplines, type Discipline} from './planning';

export type DrawingAttachment = {name: string; mime_type: string; data: string; url: string};
export function ReviewUpload({initial, connected, onImport, onDrawing, onCurrent, onSample}: {
  initial: Discipline; connected: boolean;
  onImport: (model: unknown, discipline: Discipline, source: string) => Promise<void>;
  onDrawing: (drawing: DrawingAttachment, discipline: Discipline) => void;
  onCurrent: (discipline: Discipline) => void;
  onSample: () => Promise<void>;
}) {
  const [discipline, setDiscipline] = useState(initial);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const drawing = file && !file.name.toLowerCase().endsWith('.json');
  const act = async (fn: () => Promise<void>) => {
    setError(''); setWorking(true);
    try {await fn();} catch (e) {setError(e instanceof Error ? e.message : 'Could not read this plan. Choose the file again.');}
    finally {setWorking(false);}
  };
  const read = async () => {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) throw new Error('This file is larger than 8 MB. Choose a smaller plan.');
    if (!drawing) {
      let parsed;
      try {parsed = JSON.parse(await file.text());} catch {throw new Error('This file is not valid JSON. Choose a native BuildGraph project export.');}
      await onImport(parsed?.model || parsed, discipline, file.name);
    } else {
      const mime = file.type || ({png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', pdf: 'application/pdf'} as Record<string, string>)[file.name.split('.').pop()?.toLowerCase() || ''];
      if (!['image/png', 'image/jpeg', 'image/webp', 'application/pdf'].includes(mime)) throw new Error('Choose a BuildGraph JSON, PDF, PNG, JPEG or WebP file. CAD files are not supported.');
      if (!connected) throw new Error('Drawing interpretation needs a connected AI provider. Use a native project or the sample review below.');
      const url = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('This file could not be read. Choose it again.'));
        reader.readAsDataURL(file);
      });
      onDrawing({name: file.name, mime_type: mime, data: url.slice(url.indexOf(',') + 1), url}, discipline);
    }
  };
  return <div className="modal-body review-upload">
    <p className="modal-intro">Start with one part of the plan. You can review the other systems later.</p>
    <Field label="What would you like to review?"><select value={discipline} disabled={working} onChange={e => setDiscipline(e.target.value as Discipline)}>{disciplines.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}</select></Field>
    <label className="file-drop"><Upload size={25}/><strong>{file?.name || 'Choose an existing plan'}</strong><span>BuildGraph JSON, PDF or image · up to 8 MB</span><input aria-label="Existing plan file" type="file" accept=".json,.pdf,.png,.jpg,.jpeg,.webp" disabled={working} onChange={e => {setFile(e.target.files?.[0] || null);setError('');}}/></label>
    <div className="upload-explainer"><FileCheck2 size={17}/><p><strong>Native project</strong> — validate the model and open calculated findings in a candidate revision.</p></div>
    <div className="upload-explainer"><FileText size={17}/><p><strong>PDF or image</strong> — map rooms onto the current building with AI, then confirm geometry before reviewing systems. Unmapped rooms and missing dimensions need your input.</p></div>
    {drawing && <p className="reference-note">This drawing is a layout reference. Its pipework, fire devices and engineering data are not automatically imported. {connected ? 'The next screen lets you review the request before sending it to the connected AI provider.' : 'An AI provider is not connected; native project reviews and the sample work locally.'}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    <button className="button primary full" disabled={working || !file || (!!drawing && !connected)} onClick={() => act(read)}>{working ? 'Validating plan…' : drawing ? 'Prepare drawing interpretation' : 'Upload & review model'}<ArrowRight size={15}/></button>
    <div className="upload-alternatives"><button className="text-button" disabled={working} onClick={() => onCurrent(discipline)}>Use the current model <ArrowRight size={13}/></button><button className="text-button" disabled={working} onClick={() => act(onSample)}><Play size={13}/> Try a plumbing sample</button></div>
    <p className="helper">The sample creates a candidate with direct service routes. Find clashes, preview clear routes, then compare quantities. Your accepted design is preserved.</p>
  </div>;
}
