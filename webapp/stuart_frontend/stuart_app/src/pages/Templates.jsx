import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { stuartClient } from '@/api/stuartClient';

const MODES = ['meeting', 'journal'];

export default function Templates() {
  const queryClient = useQueryClient();
  const fileInputRef = React.useRef(null);
  const [mode, setMode] = useState('meeting');
  const [q, setQ] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [showDelete, setShowDelete] = useState(false);
  const [importDraft, setImportDraft] = useState(null);

  const { data: listPayload, isLoading: listLoading } = useQuery({
    queryKey: ['templates', mode, q],
    queryFn: () => stuartClient.templates.list({ mode, q, limit: 200, offset: 0 }),
  });
  const list = useMemo(() => listPayload?.items || [], [listPayload]);

  React.useEffect(() => {
    if (!list.length) {
      setSelectedTemplateId(null);
      return;
    }
    if (!selectedTemplateId || !list.some((x) => x.template_id === selectedTemplateId)) {
      setSelectedTemplateId(list[0].template_id);
      setSelectedVersion(null);
    }
  }, [list, selectedTemplateId]);

  const { data: versionsPayload } = useQuery({
    queryKey: ['templateVersions', mode, selectedTemplateId],
    enabled: Boolean(selectedTemplateId),
    queryFn: () => stuartClient.templates.versions({ mode, template_id: selectedTemplateId }),
  });
  const versions = versionsPayload?.versions || [];

  const { data: templatePayload, isLoading: templateLoading } = useQuery({
    queryKey: ['templateRecord', mode, selectedTemplateId, selectedVersion],
    enabled: Boolean(selectedTemplateId),
    queryFn: () => stuartClient.templates.get({ mode, template_id: selectedTemplateId, version: selectedVersion || undefined }),
  });
  const template = templatePayload?.template || null;

  React.useEffect(() => {
    if (template?.descriptor?.template_title) {
      setRenameValue(template.descriptor.template_title);
    }
  }, [template?.descriptor?.template_title, selectedTemplateId]);

  const renameMutation = useMutation({
    mutationFn: async () => {
      if (!template?.descriptor?.template_id) throw new Error('No template selected.');
      return stuartClient.templates.create({
        mode,
        template_id: template.descriptor.template_id,
        template_title: renameValue,
        template_text: template.template_text,
        defaults: template.defaults || {},
      });
    },
    onSuccess: async () => {
      toast.success('Template renamed via new version.');
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      await queryClient.invalidateQueries({ queryKey: ['templateVersions'] });
      await queryClient.invalidateQueries({ queryKey: ['templateRecord'] });
    },
    onError: (err) => toast.error(String(err?.message || err)),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!template?.descriptor?.template_id) throw new Error('No template selected.');
      return stuartClient.templates.remove({ mode, template_id: template.descriptor.template_id });
    },
    onSuccess: async () => {
      setShowDelete(false);
      toast.success('Template deleted.');
      setSelectedTemplateId(null);
      setSelectedVersion(null);
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      await queryClient.invalidateQueries({ queryKey: ['templateVersions'] });
      await queryClient.invalidateQueries({ queryKey: ['templateRecord'] });
    },
    onError: (err) => toast.error(String(err?.message || err)),
  });

  async function fileToBase64(file) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    const idx = dataUrl.indexOf(',');
    return idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
  }

  async function onImportFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    const titleGuess = file.name.replace(/\.[^/.]+$/, '');
    try {
      if (lower.endsWith('.md')) {
        const text = await file.text();
        setImportDraft({
          mode,
          template_title: titleGuess || 'Imported Template',
          template_text: text,
          defaults: { include_citations: false, show_empty_sections: false },
        });
        return;
      }
      if (lower.endsWith('.txt')) {
        const rawText = await file.text();
        const payload = await stuartClient.templates.draft({
          mode,
          source_kind: 'text',
          raw_text: rawText,
          template_title: titleGuess || 'Imported Template',
          filename: file.name,
          mime_type: file.type || 'text/plain',
        });
        setImportDraft(payload?.draft || null);
        return;
      }
      if (lower.endsWith('.pdf')) {
        const bytesB64 = await fileToBase64(file);
        const payload = await stuartClient.templates.draft({
          mode,
          source_kind: 'pdf',
          bytes_b64: bytesB64,
          template_title: titleGuess || 'Imported Template',
          filename: file.name,
          mime_type: file.type || 'application/pdf',
        });
        setImportDraft(payload?.draft || null);
        return;
      }
      toast.error('Unsupported file type. Use .txt, .md, or .pdf');
    } catch (err) {
      toast.error(String(err?.message || err));
    } finally {
      event.target.value = '';
    }
  }

  const saveImportMutation = useMutation({
    mutationFn: async () => {
      if (!importDraft) throw new Error('No import draft to save.');
      return stuartClient.templates.create({
        mode: importDraft.mode || mode,
        template_title: importDraft.template_title,
        template_text: importDraft.template_text,
        defaults: importDraft.defaults || {},
      });
    },
    onSuccess: async () => {
      toast.success('Imported template saved.');
      setImportDraft(null);
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      await queryClient.invalidateQueries({ queryKey: ['templateVersions'] });
      await queryClient.invalidateQueries({ queryKey: ['templateRecord'] });
    },
    onError: (err) => toast.error(String(err?.message || err)),
  });

  return (
    <div className="min-h-screen bg-slate-50 p-4 lg:p-8">
      <div className="mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Templates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.pdf"
              className="hidden"
              onChange={onImportFileChange}
            />
            <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
              Import template (.txt/.md/.pdf)
            </Button>
            <div className="space-y-1">
              <Label>Mode</Label>
              <Select value={mode} onValueChange={(value) => { setMode(value); setSelectedVersion(null); }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <Input placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="space-y-2 max-h-[560px] overflow-auto">
              {listLoading ? <p className="text-sm text-slate-500">Loading templates...</p> : null}
              {list.map((row) => (
                <button
                  type="button"
                  key={row.template_id}
                  className={`w-full text-left rounded border px-3 py-2 ${selectedTemplateId === row.template_id ? 'border-slate-900 bg-slate-100' : 'border-slate-200 bg-white'}`}
                  onClick={() => {
                    setSelectedTemplateId(row.template_id);
                    setSelectedVersion(null);
                  }}
                >
                  <p className="text-sm font-medium">{row.template_title}</p>
                  <p className="text-xs text-slate-500">{row.template_id} • v{row.template_version}</p>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedTemplateId ? <p className="text-sm text-slate-500">No template selected.</p> : null}
            {templateLoading ? <p className="text-sm text-slate-500">Loading preview...</p> : null}
            {template || importDraft ? (
              <>
                {importDraft ? (
                  <div className="rounded border border-emerald-200 bg-emerald-50 p-3 space-y-2">
                    <p className="text-sm font-medium text-emerald-800">Import draft preview</p>
                    <Input
                      value={importDraft.template_title || ''}
                      onChange={(e) => setImportDraft((prev) => ({ ...(prev || {}), template_title: e.target.value }))}
                    />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => saveImportMutation.mutate()} disabled={saveImportMutation.isPending}>
                        Save imported template
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setImportDraft(null)}>
                        Discard
                      </Button>
                    </div>
                  </div>
                ) : null}
                {template ? (
                <div className="flex flex-col gap-2 md:flex-row md:items-end">
                  <div className="flex-1 space-y-1">
                    <Label>Template title</Label>
                    <Input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={() => renameMutation.mutate()} disabled={renameMutation.isPending || !renameValue.trim()}>
                      Rename (new version)
                    </Button>
                    <Button variant="destructive" onClick={() => setShowDelete(true)} disabled={deleteMutation.isPending}>
                      Delete
                    </Button>
                  </div>
                </div>
                ) : null}

                {template ? (
                <div className="space-y-1">
                  <Label>Version history</Label>
                  <div className="flex flex-wrap gap-2">
                    {versions.map((v) => (
                      <Button
                        key={v}
                        type="button"
                        variant={Number(selectedVersion || template.descriptor.template_version) === Number(v) ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setSelectedVersion(v)}
                      >
                        v{v}
                      </Button>
                    ))}
                  </div>
                </div>
                ) : null}

                <div className="rounded border bg-white p-4 prose prose-slate max-w-none">
                  <ReactMarkdown>{(importDraft?.template_text || template.template_text || '')}</ReactMarkdown>
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete template and all versions?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the selected template and its full version history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteMutation.mutate()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
