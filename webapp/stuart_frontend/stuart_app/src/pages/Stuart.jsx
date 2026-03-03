import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Plus, Archive, Search, Sparkles, WifiOff, Wifi, Cloud, Download, Trash2, Upload } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import AudioUploader from '@/components/stuart/AudioUploader';
import TranscriptViewer from '@/components/stuart/TranscriptViewer';
import FormalizationOutput from '@/components/stuart/FormalizationOutput';
import RunControls from '@/components/stuart/RunControls';
import SpeakerMapper from '@/components/stuart/SpeakerMapper';
import SessionCard from '@/components/stuart/SessionCard';
import SessionSearch from '@/components/stuart/SessionSearch';
import ChatInterface from '@/components/stuart/ChatInterface';
import ProcessingLog from '@/components/stuart/ProcessingLog';
import { PROFILES } from '@/components/stuart/ModeTemplateConfig';
import { stuartClient } from '@/api/stuartClient';

function safeParse(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch {
      return fallback;
    }
  }
  return value;
}

function normalizeSession(session) {
  const id = session.id ?? session.session_id;
  const createdTs = session.created_ts;
  const createdDate =
    session.created_date ??
    session.created_at ??
    (typeof createdTs === 'number' ? new Date(createdTs * 1000).toISOString() : new Date().toISOString());
  const latestStatus = session.latest_run?.status;
  const contributions = Array.isArray(session.contributions) ? session.contributions : [];
  const contributionsCount = Number(session.contributions_count ?? contributions.length ?? 0);
  const hasAudio = contributionsCount > 0;
  const isProcessing = ['running', 'queued', 'created'].includes(String(latestStatus || '').toLowerCase());
  const status =
    !hasAudio
      ? 'needs_upload'
      : isProcessing
        ? 'processing'
        : session.has_formalization
          ? 'complete'
          : session.has_transcript
            ? 'transcribed'
            : 'uploaded';
  const rawProfile = session.processing_profile || session.profile || session.execution_profile || 'LOCAL_ONLY';
  const profile = String(rawProfile || 'LOCAL_ONLY').toUpperCase();

  return {
    ...session,
    id,
    session_id: session.session_id ?? id,
    created_date: createdDate,
    status,
    profile: profile === 'CLOUD' ? 'HYBRID' : profile,
    transcript_json: safeParse(session.transcript_json ?? session.transcript_json_str, []),
    speaker_map: safeParse(session.speaker_map ?? session.speaker_map_str, {}),
    contributions: contributions,
    contributions_count: contributionsCount,
    has_audio: hasAudio,
  };
}

function normalizeFormalization(formalization) {
  return {
    ...formalization,
    output_json: safeParse(formalization.output_json ?? formalization.output_json_str, null),
    evidence_map: safeParse(formalization.evidence_map ?? formalization.evidence_map_str, []),
    processing_log: safeParse(formalization.processing_log ?? formalization.processing_log_str, []),
  };
}

function normalizeTranscriptVersion(version) {
  return {
    ...version,
    transcript_version_id: version.transcript_version_id || version.id,
    created_ts: version.created_ts ?? null,
    diarization_enabled: Boolean(version.diarization_enabled),
    asr_engine: version.asr_engine || 'default',
    segments_count: Number(version.segments_count || 0),
    active: Boolean(version.active),
  };
}

function mapUiModeToBackend(mode) {
  return mode === 'journal' ? 'journal' : 'meeting';
}

function mapRunConfigToUi(config) {
  const mode = mapUiModeToBackend(config?.mode || 'meeting');
  const diarizationEnabled = config?.diarization_enabled !== false;
  const speakers = mode === 'journal' ? 1 : diarizationEnabled ? 'auto' : 1;
  return {
    mode,
    template_id: config?.template || config?.template_id || 'default',
    retention: config?.retention_level || config?.retention || 'MED',
    speakers,
    diarization_enabled: diarizationEnabled,
    include_citations: config?.include_citations === true,
    show_empty_sections: config?.show_empty_sections === true,
    formalization_title:
      typeof config?.formalization_title === 'string' && config.formalization_title.trim()
        ? config.formalization_title.trim()
        : undefined,
  };
}

function defaultSessionTitle(sessionId) {
  const sid = String(sessionId || '').trim();
  if (!sid) return 'Session';
  return `Session ${sid.replace(/^ses_/, '').slice(0, 8).toUpperCase()}`;
}

function sanitizeExportTitle(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return '';
  return raw
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export default function Stuart() {
  const [activeTab, setActiveTab] = useState('chat');
  const [selectedSession, setSelectedSession] = useState(null);
  const [selectedFormalization, setSelectedFormalization] = useState(null);
  const [selectedTranscriptVersionId, setSelectedTranscriptVersionId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [highlightedSegments, setHighlightedSegments] = useState([]);
  const [processingLogs, setProcessingLogs] = useState([]);
  const [sessionMetaById, setSessionMetaById] = useState(() => {
    try {
      const raw = localStorage.getItem('stuart_session_meta_v1');
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  });
  const [activeRunId, setActiveRunId] = useState(null);
  const [isEditingSessionTitle, setIsEditingSessionTitle] = useState(false);
  const [sessionTitleDraft, setSessionTitleDraft] = useState('');
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportType, setExportType] = useState('full_bundle');
  const [transcriptFormats, setTranscriptFormats] = useState(['txt']);
  const [formalizationFormats, setFormalizationFormats] = useState(['pdf']);
  const [isExporting, setIsExporting] = useState(false);
  const lastRunStatusRef = useRef(null);
  const sessionTitleInputRef = useRef(null);

  const queryClient = useQueryClient();

  useEffect(() => {
    try {
      localStorage.setItem('stuart_session_meta_v1', JSON.stringify(sessionMetaById));
    } catch {
      // ignore storage errors
    }
  }, [sessionMetaById]);

  const { data: sessionsRaw = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => stuartClient.sessions.list(),
  });

  const sessions = useMemo(
    () =>
      sessionsRaw.map(normalizeSession).map((s) => {
        const local = sessionMetaById[s.id] || {};
        return {
          ...s,
          audio_filename: s.audio_filename || local.audio_filename,
          duration_seconds: s.duration_seconds ?? local.duration_seconds,
          title: s.title || local.title || defaultSessionTitle(s.id),
        };
      }),
    [sessionsRaw, sessionMetaById],
  );

  useEffect(() => {
    if (!selectedSession?.id) return;
    const next = sessions.find((s) => s.id === selectedSession.id);
    if (next) {
      setSelectedSession((prev) => ({
        ...next,
        audio_filename: next.audio_filename || prev?.audio_filename,
        duration_seconds: next.duration_seconds ?? prev?.duration_seconds,
      }));
    }
  }, [sessions, selectedSession?.id]);

  useEffect(() => {
    if (!isEditingSessionTitle) return;
    sessionTitleInputRef.current?.focus();
  }, [isEditingSessionTitle]);

  useEffect(() => {
    if (selectedSession || sessions.length === 0) return;
    const url = new URL(window.location.href);
    const requestedSessionId = url.searchParams.get('session');
    if (!requestedSessionId) return;
    const match = sessions.find((s) => String(s.id) === requestedSessionId);
    if (match) {
      setSelectedSession(match);
    }
  }, [sessions, selectedSession]);

  const { data: formalizationsRaw = [] } = useQuery({
    queryKey: ['formalizations', selectedSession?.id],
    queryFn: () => stuartClient.formalizations.list(selectedSession.id),
    enabled: Boolean(selectedSession?.id),
  });

  const formalizations = useMemo(
    () => formalizationsRaw.map(normalizeFormalization),
    [formalizationsRaw],
  );
  const activeSpeakerRunId = selectedFormalization?.run_id || formalizations[0]?.run_id || activeRunId || null;
  const { data: runSpeakers = [] } = useQuery({
    queryKey: ['run-speakers', activeSpeakerRunId],
    queryFn: () => stuartClient.runs.speakers(activeSpeakerRunId),
    enabled: Boolean(activeSpeakerRunId),
  });

  const { data: transcriptVersionsRaw = [] } = useQuery({
    queryKey: ['transcripts', selectedSession?.id],
    queryFn: () => stuartClient.transcripts.list(selectedSession.id),
    enabled: Boolean(selectedSession?.id),
  });

  const transcriptVersions = useMemo(
    () => transcriptVersionsRaw.map(normalizeTranscriptVersion),
    [transcriptVersionsRaw],
  );

  useEffect(() => {
    const active = transcriptVersions.find((t) => t.active);
    const nextId = active?.transcript_version_id || transcriptVersions[0]?.transcript_version_id || null;
    setSelectedTranscriptVersionId((prev) => prev || nextId);
  }, [transcriptVersions]);

  useEffect(() => {
    if (!selectedSession?.id) {
      setSelectedTranscriptVersionId(null);
    }
  }, [selectedSession?.id]);

  const { data: selectedTranscriptPayload } = useQuery({
    queryKey: ['transcript-version', selectedTranscriptVersionId],
    queryFn: () => stuartClient.transcripts.get(selectedTranscriptVersionId),
    enabled: Boolean(selectedTranscriptVersionId),
  });

  const selectedSessionView = useMemo(() => {
    if (!selectedSession) return null;
    const latestTranscript = transcriptVersions.find((t) => t.transcript_version_id === selectedTranscriptVersionId) || transcriptVersions[0];
    if (!latestTranscript) return selectedSession;
    const transcriptObj = selectedTranscriptPayload?.transcript || {};
    const transcript = Array.isArray(transcriptObj.segments) ? transcriptObj.segments : [];
    const speakerMap = transcriptObj.speaker_map && typeof transcriptObj.speaker_map === 'object'
      ? transcriptObj.speaker_map
      : (selectedSession.speaker_map || {});
    return {
      ...selectedSession,
      transcript_json: transcript,
      speaker_map: speakerMap,
      transcript_version_id: latestTranscript.transcript_version_id,
      transcript_meta: {
        diarization_enabled: latestTranscript.diarization_enabled,
        asr_engine: latestTranscript.asr_engine,
        segments_count: latestTranscript.segments_count,
      },
    };
  }, [selectedSession, transcriptVersions, selectedTranscriptVersionId, selectedTranscriptPayload]);

  const { data: activeRunStatus } = useQuery({
    queryKey: ['run-status', activeRunId],
    queryFn: () => stuartClient.runs.status(activeRunId),
    enabled: Boolean(activeRunId),
    refetchInterval: 1500,
  });

  useEffect(() => {
    if (!activeRunStatus || !activeRunId) return;
    const state = activeRunStatus.state || {};
    const status = state.status || activeRunStatus.status || 'running';
    const stage = state.stage || activeRunStatus.progress?.stage || 'running';
    const progress = activeRunStatus.progress?.progress;

    if (status === 'running' || status === 'queued' || status === 'created') {
      setIsProcessing(true);
      setProcessingLogs((prev) => [
        ...prev.filter((l) => l.step !== 'formalize'),
        {
          step: 'formalize',
          status: 'running',
          message: `Run ${activeRunId} in progress`,
          timestamp: new Date(),
          details: { stage, progress: progress ?? 0 },
        },
      ]);
    }

    if (status !== lastRunStatusRef.current) {
      lastRunStatusRef.current = status;

      if (status === 'succeeded') {
        setIsProcessing(false);
        setProcessingLogs((prev) => [
          ...prev.filter((l) => l.step !== 'formalize'),
          {
            step: 'formalize',
            status: 'completed',
            message: `Run ${activeRunId} completed`,
            timestamp: new Date(),
            details: { stage, progress: progress ?? 100 },
          },
        ]);

        const finishedRunId = activeRunId;
        const currentSessionId = selectedSession?.id;
        const refreshAfterSuccess = async () => {
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['sessions'] }),
            queryClient.invalidateQueries({ queryKey: ['formalizations', currentSessionId] }),
            queryClient.invalidateQueries({ queryKey: ['transcripts', currentSessionId] }),
          ]);
          if (!currentSessionId) return;
          const latestFormalizations = await queryClient.fetchQuery({
            queryKey: ['formalizations', currentSessionId],
            queryFn: () => stuartClient.formalizations.list(currentSessionId),
          });
          const normalized = latestFormalizations.map(normalizeFormalization);
          const matching = normalized.find((f) => f.id === finishedRunId || f.run_id === finishedRunId);
          setSelectedFormalization(matching || normalized[0] || null);
          setActiveTab('formalizations');
        };

        refreshAfterSuccess().catch(() => {
          // Keep the UI usable even if refresh fails transiently.
        });
        toast.success(`Run ${finishedRunId} completed`);
        setActiveRunId(null);
      } else if (status === 'cancelled') {
        setIsProcessing(false);
        setProcessingLogs((prev) => [
          ...prev.filter((l) => l.step !== 'formalize'),
          {
            step: 'formalize',
            status: 'failed',
            message: `Run ${activeRunId} cancelled`,
            timestamp: new Date(),
          },
        ]);
        toast.info(`Run ${activeRunId} cancelled`);
        setActiveRunId(null);
      } else if (status === 'failed') {
        setIsProcessing(false);
        setProcessingLogs((prev) => [
          ...prev.filter((l) => l.step !== 'formalize'),
          {
            step: 'formalize',
            status: 'failed',
            message: state.error || `Run ${activeRunId} failed`,
            timestamp: new Date(),
          },
        ]);
        toast.error(state.error || `Run ${activeRunId} failed`);
        setActiveRunId(null);
      }
    }
  }, [activeRunStatus, activeRunId, queryClient, selectedSession?.id]);

  const handleUploadComplete = async ({ uploadResult, filename, duration_seconds }) => {
    const sessionId = uploadResult?.session_id;
    if (!sessionId) {
      throw new Error('Upload succeeded but backend did not return session_id.');
    }

    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    const refreshed = await queryClient.fetchQuery({
      queryKey: ['sessions'],
      queryFn: () => stuartClient.sessions.list(),
    });
    const normalized = refreshed.map(normalizeSession);
    const matched = normalized.find((s) => s.id === sessionId);

    const matchedOrFallback =
      matched || {
        id: sessionId,
        session_id: sessionId,
        title: filename.replace(/\.[^/.]+$/, '') || defaultSessionTitle(sessionId),
        audio_filename: filename,
        duration_seconds,
        status: 'uploaded',
        transcript_json: [],
        speaker_map: {},
        contributions: ['upload'],
        contributions_count: 1,
        has_audio: true,
      };

    setSelectedSession(matchedOrFallback);
    setActiveTab('chat');
    setShowUploadPanel(false);
    toast.success('Upload complete. Select mode/template when ready, then run.');
  };

  const handleTranscribe = async (config) => {
    if (!selectedSession?.id) {
      toast.error('No session selected');
      return;
    }
    if ((selectedSession?.contributions_count || 0) <= 0 && !selectedSession?.has_audio) {
      toast.error('Upload audio before running.');
      return;
    }

    setIsProcessing(true);
    setProcessingLogs([
      { step: 'transcribe', status: 'running', message: 'Submitting transcribe run...', timestamp: new Date() },
    ]);
    let submittedRunId = null;
    try {
      const resp = await stuartClient.transcribe({
        session_id: selectedSession.id,
        mode: config?.mode || 'meeting',
        diarization_enabled: config?.diarization_enabled !== false,
      });
      submittedRunId = resp?.run_id || null;
      if (submittedRunId) {
        setActiveRunId(submittedRunId);
      }
      await queryClient.invalidateQueries({ queryKey: ['sessions'] });
      setProcessingLogs([
        { step: 'transcribe', status: 'running', message: `Transcribe run submitted (${submittedRunId || 'pending'})`, timestamp: new Date() },
      ]);
      toast.success(`Transcribe submitted${submittedRunId ? ` (${submittedRunId})` : ''}`);
    } catch (error) {
      setProcessingLogs([
        { step: 'transcribe', status: 'failed', message: error.message, timestamp: new Date() },
      ]);
      toast.error(error.message || 'Transcribe failed');
      setIsProcessing(false);
    } finally {
      if (!submittedRunId) {
        setIsProcessing(false);
      }
    }
  };

  const handleSelectTranscriptVersion = async (transcriptVersionId) => {
    setSelectedTranscriptVersionId(transcriptVersionId || null);
    if (!selectedSession?.id || !transcriptVersionId) return;
    try {
      await stuartClient.transcripts.setActive(selectedSession.id, transcriptVersionId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['transcripts', selectedSession.id] }),
        queryClient.invalidateQueries({ queryKey: ['transcript-version', transcriptVersionId] }),
        queryClient.invalidateQueries({ queryKey: ['sessions'] }),
      ]);
    } catch (error) {
      toast.error(error.message || 'Failed to set active transcript version');
    }
  };

  const handleDeleteTranscriptVersion = async () => {
    if (!selectedSession?.id || !selectedTranscriptVersionId) return;
    const current = transcriptVersions.find((t) => t.transcript_version_id === selectedTranscriptVersionId);
    const label = current?.transcript_version_id || selectedTranscriptVersionId;
    const okBasic = window.confirm(`Delete transcript version "${label}"?`);
    if (!okBasic) return;

    try {
      await stuartClient.transcripts.remove(selectedTranscriptVersionId, { cascade: false });
    } catch (error) {
      const message = String(error?.message || '');
      if (error?.status === 409 || message.includes('TRANSCRIPT_HAS_DEPENDENTS')) {
        let details = '';
        const deps = error?.body?.dependents || {};
        const consumers = Array.isArray(deps?.consumers) ? deps.consumers.map((r) => r.run_id).filter(Boolean) : [];
        const producers = Array.isArray(deps?.producers) ? deps.producers.map((r) => r.run_id).filter(Boolean) : [];
        const runList = [...new Set([...consumers, ...producers])];
        if (runList.length) {
          details = `\n\nDependent runs:\n- ${runList.join('\n- ')}`;
        }
        const okCascade = window.confirm(
          `This transcript has dependent formalizations. Delete transcript and dependent runs?${details}`
        );
        if (!okCascade) return;
        await stuartClient.transcripts.remove(selectedTranscriptVersionId, { cascade: true });
      } else {
        throw error;
      }
    }

    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['transcripts', selectedSession.id] }),
      queryClient.invalidateQueries({ queryKey: ['formalizations', selectedSession.id] }),
      queryClient.invalidateQueries({ queryKey: ['sessions'] }),
    ]);
    setSelectedFormalization(null);
    setSelectedTranscriptVersionId(null);
    toast.success(`Deleted transcript version ${label}`);
  };

  const handleRun = async (config) => {
    if (!selectedSession?.id) {
      toast.error('No session selected');
      return;
    }
    if ((selectedSession?.contributions_count || 0) <= 0 && !selectedSession?.has_audio) {
      toast.error('Upload audio before running.');
      return;
    }

    setIsProcessing(true);
    setProcessingLogs([
      { step: 'formalize', status: 'running', message: 'Submitting formalization run...', timestamp: new Date() },
    ]);

    let submittedRunId = null;
    try {
      const runResponse = await stuartClient.runs.create({
        session_id: selectedSession.id,
        transcript_version_id: selectedSessionView?.transcript_version_id || null,
        ui: mapRunConfigToUi(config),
      });
      if (runResponse?.run_id) {
        setActiveRunId(runResponse.run_id);
        submittedRunId = runResponse.run_id;
      }

      if (runResponse?.formalization) {
        setSelectedFormalization(normalizeFormalization(runResponse.formalization));
      }

      await queryClient.invalidateQueries({ queryKey: ['sessions'] });

      setProcessingLogs((prev) => [
        ...prev.filter((l) => l.step !== 'formalize'),
        {
          step: 'formalize',
          status: 'running',
          message: `Run submitted${runResponse?.run_id ? ` (${runResponse.run_id})` : ''}`,
          timestamp: new Date(),
          data_sent_externally: config.profile !== 'LOCAL_ONLY',
        },
      ]);

      toast.success(`Run submitted${runResponse?.run_id ? ` (${runResponse.run_id})` : ''}`);
    } catch (error) {
      setProcessingLogs((prev) => [
        ...prev.filter((l) => l.step !== 'formalize'),
        { step: 'formalize', status: 'failed', message: error.message, timestamp: new Date() },
      ]);
      toast.error(error.message || 'Formalization failed');
      setIsProcessing(false);
    } finally {
      if (!submittedRunId) {
        setIsProcessing(false);
      }
    }
  };

  const handleRenameFormalization = async (formalization, title) => {
    const runId = formalization?.run_id || formalization?.id;
    const nextTitle = String(title || '').trim();
    if (!runId || !nextTitle) {
      toast.error('Invalid formalization title');
      return;
    }
    try {
      await stuartClient.runs.update(runId, { formalization_title: nextTitle });
      if (selectedSession?.id) {
        await queryClient.invalidateQueries({ queryKey: ['formalizations', selectedSession.id] });
      }
      setSelectedFormalization((prev) =>
        prev && (prev.run_id === runId || prev.id === runId) ? { ...prev, title: nextTitle } : prev
      );
      toast.success('Formalization renamed');
    } catch (error) {
      toast.error(error.message || 'Failed to rename formalization');
    }
  };

  const handleSpeakerMapUpdate = async (speakerMap) => {
    const transcriptVersionId = selectedSessionView?.transcript_version_id || selectedTranscriptVersionId;
    if (!transcriptVersionId) {
      toast.error('No transcript version selected');
      return;
    }

    try {
      const res = await stuartClient.transcripts.setSpeakerMap(transcriptVersionId, {
        mapping: speakerMap,
        author: 'web',
      });
      const savedMap = res?.speaker_map && typeof res.speaker_map === 'object' ? res.speaker_map : {};
      queryClient.setQueryData(['transcript-version', transcriptVersionId], (prev) => {
        if (!prev || typeof prev !== 'object') return prev;
        const transcript = prev.transcript && typeof prev.transcript === 'object' ? prev.transcript : {};
        return {
          ...prev,
          transcript: {
            ...transcript,
            speaker_map: savedMap,
            speaker_overlay_id: res?.speaker_overlay_id ?? null,
          },
        };
      });
      setSelectedSession((prev) => (prev ? { ...prev, speaker_map: savedMap } : prev));

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['sessions'] }),
        queryClient.invalidateQueries({ queryKey: ['transcripts', selectedSession?.id] }),
        queryClient.invalidateQueries({ queryKey: ['transcript-version', transcriptVersionId] }),
      ]);
      toast.success('Speaker names saved.');
    } catch (error) {
      toast.error(error.message || 'Failed to save speaker names');
    }
  };

  const handleChatMessage = async (message, options, onResponse) => {
    if (!selectedSession?.id) {
      onResponse('Please select a session first.');
      return;
    }

    const text = String(message || '').trim();
    const exportMatch = text.match(/^\/export(?:\s+(full_bundle|transcript_only|formalization_only|dev_bundle))?$/i);
    if (exportMatch) {
      const exportType = exportMatch[1] || 'full_bundle';
      try {
        await downloadSessionExport({
          selectedType: exportType,
          selectedTranscriptFormats: exportType === 'formalization_only' ? [] : ['txt'],
          selectedFormalizationFormats: exportType === 'transcript_only' ? [] : ['pdf'],
        });
        onResponse(`Export complete (${exportType}).`);
      } catch (error) {
        onResponse(error.message || `Export failed (${exportType}).`);
      }
      return;
    }

    setIsProcessing(true);
    try {
      const scope = options?.scope === 'global' ? 'global' : 'session';
      const requestPayload = {
        session_id: selectedSession.id,
        message,
        attachments: Array.isArray(options?.attachments) ? options.attachments : [],
      };
      const response =
        scope === 'global'
          ? await stuartClient.chat.global(requestPayload)
          : await stuartClient.chat.session(requestPayload);
      if (typeof response === 'string') {
        onResponse(response);
      } else if (response?.preview?.summary) {
        onResponse(response.preview.summary);
      } else if (response?.clarify?.question) {
        onResponse(response.clarify.question);
      } else if (response?.answer || response?.message) {
        onResponse(response.answer || response.message);
      } else {
        onResponse('Request accepted. Check run progress/results.');
      }
    } catch (error) {
      const msg = String(error?.message || '');
      if (options?.scope === 'global' && /not[_\s-]*implemented|501|404/i.test(msg)) {
        onResponse('Global chat is not implemented yet in this runtime.');
      } else {
        onResponse(msg || 'I encountered an error processing your request.');
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleChatUploadAttachments = async (files) => {
    if (!selectedSession?.id) return [];
    const uploaded = [];
    for (const file of files) {
      const result = await stuartClient.upload(file, { sessionId: selectedSession.id });
      uploaded.push({
        filename: file.name,
        size_bytes: file.size,
        mime_type: file.type || 'application/octet-stream',
        session_id: result?.session_id || selectedSession.id,
      });
    }
    await queryClient.invalidateQueries({ queryKey: ['sessions'] });
    return uploaded;
  };

  const downloadSessionExport = async ({
    selectedType,
    selectedTranscriptFormats,
    selectedFormalizationFormats,
  }) => {
    if (!selectedSession?.id) {
      throw new Error('No session selected');
    }

    const params = {
      format: 'zip',
      export_type: selectedType || 'full_bundle',
    };
    if (params.export_type !== 'dev_bundle' && selectedTranscriptFormats?.length) {
      params.transcript_formats = selectedTranscriptFormats.join(',');
    }
    if (params.export_type !== 'dev_bundle' && selectedFormalizationFormats?.length) {
      params.formalization_formats = selectedFormalizationFormats.join(',');
    }

    const blob = await stuartClient.exportSession(selectedSession.id, params);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const titleSlug = sanitizeExportTitle(selectedSession.title || '');
    const baseName = titleSlug
      ? `${selectedSession.id}__${titleSlug}__export_${params.export_type}.zip`
      : `${selectedSession.id}__export_${params.export_type}.zip`;
    link.href = url;
    link.download = baseName;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleExportZip = async () => {
    if (!selectedSession?.id) {
      toast.error('No session selected');
      return;
    }

    const needsTranscript = exportType === 'full_bundle' || exportType === 'transcript_only';
    const needsFormalization = exportType === 'full_bundle' || exportType === 'formalization_only';
    if (needsTranscript && transcriptFormats.length === 0) {
      toast.error('Select at least one transcript format');
      return;
    }
    if (needsFormalization && formalizationFormats.length === 0) {
      toast.error('Select at least one formalization format');
      return;
    }

    try {
      setIsExporting(true);
      await downloadSessionExport({
        selectedType: exportType,
        selectedTranscriptFormats: transcriptFormats,
        selectedFormalizationFormats: formalizationFormats,
      });
      setExportModalOpen(false);
      toast.success('Export complete');
    } catch (error) {
      toast.error(error.message || 'Export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDownloadPdf = async (formalization) => {
    const pdfUrl = formalization?.pdf_url || formalization?.output_json?.downloads?.primary?.pdf?.url;
    if (!pdfUrl) {
      toast.error('No PDF available for this output.');
      return;
    }

    try {
      const res = await fetch(pdfUrl);
      if (!res.ok) {
        throw new Error(`PDF download failed (${res.status})`);
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `${selectedSession?.title || 'session'}_${formalization?.id || 'formalization'}.pdf`;
      link.click();
      URL.revokeObjectURL(blobUrl);
    } catch (error) {
      toast.error(error.message || 'PDF download failed');
    }
  };

  const handleDownloadMarkdown = async (formalization) => {
    const md = formalization?.output_markdown;
    if (!md) {
      toast.error('No markdown output available.');
      return;
    }
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = `${selectedSession?.title || 'session'}_${formalization?.id || 'formalization'}.md`;
    link.click();
    URL.revokeObjectURL(blobUrl);
  };

  const handleDownloadText = async (formalization) => {
    const txtUrl = formalization?.output_json?.downloads?.primary?.txt?.url;
    if (!txtUrl) {
      toast.error('No text output available.');
      return;
    }

    try {
      const res = await fetch(txtUrl);
      if (!res.ok) {
        throw new Error(`Text download failed (${res.status})`);
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `${selectedSession?.title || 'session'}_${formalization?.id || 'formalization'}.txt`;
      link.click();
      URL.revokeObjectURL(blobUrl);
    } catch (error) {
      toast.error(error.message || 'Text download failed');
    }
  };

  const handlePrintPdf = async (formalization) => {
    const pdfUrl = formalization?.pdf_url || formalization?.output_json?.downloads?.primary?.pdf?.url;
    if (!pdfUrl) {
      toast.error('No PDF available for this output.');
      return;
    }

    try {
      const res = await fetch(pdfUrl);
      if (!res.ok) {
        throw new Error(`PDF print failed (${res.status})`);
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);

      const preview = window.open(
        blobUrl,
        'stuart_pdf_print_preview',
        'popup=yes,width=1000,height=740,left=120,top=80,resizable=yes,scrollbars=yes',
      );
      if (!preview) {
        URL.revokeObjectURL(blobUrl);
        throw new Error('Popup blocked. Allow popups to open print preview.');
      }
      preview.focus();
      toast.info('Print preview opened. Use Ctrl/Cmd+P in the popup to print.');
      preview.addEventListener('beforeunload', () => {
        URL.revokeObjectURL(blobUrl);
      });
    } catch (error) {
      toast.error(error.message || 'PDF print failed');
    }
  };

  const transcriptFormatsEnabled = exportType === 'full_bundle' || exportType === 'transcript_only';
  const formalizationFormatsEnabled = exportType === 'full_bundle' || exportType === 'formalization_only';

  const toggleTranscriptFormat = (fmt, checked) => {
    setTranscriptFormats((prev) => {
      const next = new Set(prev);
      if (checked) next.add(fmt);
      else next.delete(fmt);
      return Array.from(next);
    });
  };

  const toggleFormalizationFormat = (fmt, checked) => {
    setFormalizationFormats((prev) => {
      const next = new Set(prev);
      if (checked) next.add(fmt);
      else next.delete(fmt);
      return Array.from(next);
    });
  };

  const commitSessionRename = () => {
    if (!selectedSession?.id) return;
    const trimmed = sessionTitleDraft.trim();
    setIsEditingSessionTitle(false);
    if (!trimmed) return;

    setSessionMetaById((prev) => ({
      ...prev,
      [selectedSession.id]: {
        ...(prev[selectedSession.id] || {}),
        title: trimmed,
      },
    }));
    setSelectedSession((prev) => (prev ? { ...prev, title: trimmed } : prev));
    stuartClient.sessions.update(selectedSession.id, { title: trimmed }).catch(() => {
      // Keep UI rename local even if patch endpoint fails.
    });
    toast.success('Session name updated');
  };

  const handleRenameSession = () => {
    if (!selectedSession?.id) return;
    setSessionTitleDraft('');
    setIsEditingSessionTitle(true);
  };

  const handleDeleteSession = async () => {
    if (!selectedSession?.id) return;
    const name = selectedSession.title || defaultSessionTitle(selectedSession.id);
    const ok = window.confirm(`Delete session "${name}"?\n\nThis will remove linked runs, uploads, and overlays for this session.`);
    if (!ok) return;

    try {
      if (activeRunId) {
        try {
          await stuartClient.runs.cancel(activeRunId);
        } catch {
          // Best-effort cancel; proceed with deletion.
        }
      }
      await stuartClient.sessions.remove(selectedSession.id);
      setSessionMetaById((prev) => {
        const next = { ...prev };
        delete next[selectedSession.id];
        return next;
      });
      setSelectedSession(null);
      setSelectedFormalization(null);
      setProcessingLogs([]);
      setActiveRunId(null);
      setIsProcessing(false);
      setShowUploadPanel(false);
      await queryClient.invalidateQueries({ queryKey: ['sessions'] });
      toast.success('Session deleted');
    } catch (error) {
      toast.error(error.message || 'Failed to delete session');
    }
  };

  const handleDeleteRun = async (formalization) => {
    const runId = formalization?.run_id || formalization?.id;
    if (!runId) return;
    const ok = window.confirm(`Delete run "${runId}"?\n\nThis removes outputs/evidence for this run.`);
    if (!ok) return;

    try {
      await stuartClient.runs.remove(runId);
      if ((selectedFormalization?.run_id || selectedFormalization?.id) === runId) {
        setSelectedFormalization(null);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['formalizations', selectedSession?.id] }),
        queryClient.invalidateQueries({ queryKey: ['sessions'] }),
      ]);
      toast.success(`Deleted run ${runId}`);
    } catch (error) {
      toast.error(error.message || 'Failed to delete run');
    }
  };

  const handleCreateSession = async () => {
    setSelectedSession(null);
    setSelectedFormalization(null);
    setSelectedTranscriptVersionId(null);
    setActiveRunId(null);
    setIsProcessing(false);
    setProcessingLogs([]);
    setShowUploadPanel(true);
    toast.info('Upload audio to create a new session.');
  };

  const ProfileIcon =
    selectedSession?.profile === 'LOCAL_ONLY'
      ? WifiOff
      : selectedSession?.profile === 'CLOUD'
        ? Cloud
        : Wifi;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
                <Sparkles className="h-5 w-5 text-white" />
              </div>
              <div>
                <h1 className="font-bold text-xl text-slate-800">Stuart</h1>
                <p className="text-xs text-slate-500">Voice Intelligence System</p>
              </div>
            </div>

            {selectedSession && (
              <div className="flex items-center gap-2">
                <Badge className={`text-xs ${PROFILES[selectedSession.profile]?.color || 'bg-slate-500'} text-white`}>
                  <ProfileIcon className="h-3 w-3 mr-1" />
                  {PROFILES[selectedSession.profile]?.label || 'Hybrid'}
                </Badge>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-3">
            <div className="sticky top-24 space-y-4">
              <button
                className="w-full relative group overflow-hidden rounded-lg"
                onClick={handleCreateSession}
              >
                <div className="relative px-6 py-3 bg-gradient-to-b from-amber-500 via-amber-600 to-amber-700 shadow-lg border-2 border-amber-400/60">
                  <div className="absolute inset-0 bg-gradient-to-b from-amber-300/40 to-transparent" />
                  <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.3),transparent_60%)]" />
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-200 to-transparent" />
                  <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-t from-amber-900/60 to-transparent" />

                  <div className="relative flex items-center justify-center gap-2 font-bold text-base text-amber-50 drop-shadow-[0_2px_2px_rgba(0,0,0,0.5)] group-hover:scale-105 transition-transform">
                    <Plus className="h-5 w-5" />
                    <span className="tracking-wide">New Session</span>
                  </div>
                </div>

                <div className="absolute inset-0 shadow-[inset_0_0_12px_rgba(0,0,0,0.3)] rounded-lg pointer-events-none" />
              </button>

              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => setShowUploadPanel((prev) => !prev)}
              >
                <Upload className="h-4 w-4 mr-2" />
                {showUploadPanel ? 'Hide Upload' : 'Upload Audio'}
              </Button>

              <Tabs defaultValue="recent" className="w-full">
                <TabsList className="w-full bg-slate-100">
                  <TabsTrigger value="recent" className="flex-1">
                    <Archive className="h-4 w-4 mr-1.5" />
                    Recent
                  </TabsTrigger>
                  <TabsTrigger value="search" className="flex-1">
                    <Search className="h-4 w-4 mr-1.5" />
                    Search
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="recent" className="mt-3">
                  <ScrollArea className="h-[calc(100vh-280px)]">
                    <div className="space-y-2 pr-2">
                      {sessionsLoading ? (
                        <p className="text-sm text-slate-400 text-center py-4">Loading...</p>
                      ) : sessions.length === 0 ? (
                        <p className="text-sm text-slate-400 text-center py-4">No sessions yet</p>
                      ) : (
                        sessions.map((session) => (
                          <SessionCard
                            key={session.id}
                            session={session}
                            isSelected={selectedSession?.id === session.id}
                            onClick={(s) => {
                              setSelectedSession(s);
                              setSelectedFormalization(null);
                            }}
                          />
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="search" className="mt-3">
                  <SessionSearch
                    sessions={sessions}
                    onSessionSelect={(s) => {
                      setSelectedSession(s);
                      setActiveTab('session');
                    }}
                    onJumpToTimestamp={(session) => {
                      setSelectedSession(session);
                      setActiveTab('session');
                    }}
                  />
                </TabsContent>
              </Tabs>
            </div>
          </aside>

          <div className="col-span-12 lg:col-span-9">
            {!selectedSession ? (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <div className="text-center py-8">
                  <h2 className="text-2xl font-semibold text-slate-800 mb-2">Start a New Session</h2>
                  <p className="text-slate-500">Upload an audio recording to begin extracting insights</p>
                </div>

                <AudioUploader onUploadComplete={handleUploadComplete} />
              </motion.div>
            ) : (
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedSession.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="space-y-6"
                >
                  {showUploadPanel && (
                    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-slate-700">Upload Audio</p>
                        <Button type="button" variant="ghost" size="sm" onClick={() => setShowUploadPanel(false)}>
                          Hide
                        </Button>
                      </div>
                      <AudioUploader
                        onUploadComplete={handleUploadComplete}
                        uploadOptions={{ sessionId: selectedSession.id }}
                      />
                    </div>
                  )}

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      {isEditingSessionTitle ? (
                        <input
                          ref={sessionTitleInputRef}
                          type="text"
                          value={sessionTitleDraft}
                          placeholder={selectedSession.title || defaultSessionTitle(selectedSession.id)}
                          onChange={(e) => setSessionTitleDraft(e.target.value)}
                          onBlur={commitSessionRename}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              commitSessionRename();
                            } else if (e.key === 'Escape') {
                              setIsEditingSessionTitle(false);
                              setSessionTitleDraft('');
                            }
                          }}
                          className="w-full bg-transparent border-none p-0 m-0 text-xl font-semibold text-slate-800 placeholder:text-slate-400 focus:outline-none"
                        />
                      ) : (
                        <h2 className="text-xl font-semibold text-slate-800">
                          {selectedSession.title || defaultSessionTitle(selectedSession.id)}
                        </h2>
                      )}
                      <p className="text-sm text-slate-500">{selectedSession.audio_filename}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {isProcessing && activeRunId && (
                        <Button
                          variant="outline"
                          onClick={async () => {
                            try {
                              await stuartClient.runs.cancel(activeRunId);
                              setIsProcessing(false);
                              setActiveRunId(null);
                              setProcessingLogs((prev) => [
                                ...prev,
                                { step: 'formalize', status: 'failed', message: `Run ${activeRunId} cancelled`, timestamp: new Date() },
                              ]);
                              toast.info(`Cancelled run ${activeRunId}`);
                            } catch (error) {
                              toast.error(error.message || 'Failed to cancel run');
                            }
                          }}
                        >
                          Cancel Run
                        </Button>
                      )}
                      <Button variant="outline" onClick={handleRenameSession}>
                        Rename Session
                      </Button>
                      <Button variant="outline" onClick={handleDeleteSession} className="text-red-700 border-red-300 hover:bg-red-50">
                        <Trash2 className="h-4 w-4 mr-1.5" />
                        Delete Session
                      </Button>
                      <Button variant="outline" onClick={() => setExportModalOpen(true)}>
                        <Download className="h-4 w-4 mr-1.5" />
                        Export ZIP
                      </Button>
                    </div>
                  </div>

                  <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="bg-slate-100">
                      <TabsTrigger value="session">Session</TabsTrigger>
                      <TabsTrigger value="chat">Chat</TabsTrigger>
                      <TabsTrigger value="formalizations">Outputs ({formalizations.length})</TabsTrigger>
                    </TabsList>

                    <TabsContent value="session" className="mt-6">
                      <div className="grid grid-cols-12 gap-6">
                        <div className="col-span-12 xl:col-span-7 space-y-6">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm text-slate-500">Transcript Version</div>
                            <div className="flex items-center gap-2">
                              <Select
                                value={selectedTranscriptVersionId || undefined}
                                onValueChange={handleSelectTranscriptVersion}
                              >
                                <SelectTrigger className="w-[320px]">
                                  <SelectValue placeholder="Select transcript version" />
                                </SelectTrigger>
                                <SelectContent>
                                  {transcriptVersions.map((version) => {
                                    const vid = version.transcript_version_id;
                                    const created = version.created_ts
                                      ? new Date(version.created_ts * 1000).toLocaleString()
                                      : 'unknown';
                                    return (
                                      <SelectItem key={vid} value={vid}>
                                        {`${String(vid).replace(/^trv_/, '').slice(0, 10)} • ${created} • ${version.segments_count} segments${version.active ? ' • ACTIVE' : ''}`}
                                      </SelectItem>
                                    );
                                  })}
                                </SelectContent>
                              </Select>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleDeleteTranscriptVersion}
                                disabled={!selectedTranscriptVersionId}
                                className="text-red-700 border-red-300 hover:bg-red-50"
                              >
                                <Trash2 className="h-4 w-4 mr-1.5" />
                                Delete
                              </Button>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-slate-500">
                            <Badge variant={selectedSessionView?.transcript_meta?.diarization_enabled ? 'default' : 'secondary'}>
                              {selectedSessionView?.transcript_meta?.diarization_enabled ? 'Diarization ON' : 'Diarization OFF'}
                            </Badge>
                            <Badge variant="outline">
                              ASR: {selectedSessionView?.transcript_meta?.asr_engine || 'default'}
                            </Badge>
                            <Badge variant="outline">
                              Segments: {selectedSessionView?.transcript_meta?.segments_count ?? (selectedSessionView?.transcript_json || []).length}
                            </Badge>
                          </div>
                          <TranscriptViewer
                            transcript={selectedSessionView?.transcript_json || []}
                            speakerMap={selectedSessionView?.speaker_map || {}}
                            highlightedSegments={highlightedSegments}
                            onSegmentClick={(seg) => setHighlightedSegments([seg.segment_id])}
                          />

                          {(() => {
                            const transcriptSpeakerIds =
                              selectedSessionView?.transcript_json
                                ?.filter((s) => Boolean(s.speaker))
                                .map((s) => s.speaker) || [];
                            const allSpeakerIds = [...new Set([...(runSpeakers || []), ...transcriptSpeakerIds])];
                            if (allSpeakerIds.length === 0) return null;
                            return (
                              <SpeakerMapper
                                speakerIds={allSpeakerIds}
                                transcript={selectedSessionView.transcript_json}
                                speakerMap={selectedSessionView.speaker_map || {}}
                                onSpeakerMapUpdate={handleSpeakerMapUpdate}
                              />
                            );
                          })()}
                        </div>

                        <div className="col-span-12 xl:col-span-5 space-y-6">
                          <RunControls
                            session={selectedSession}
                            onTranscribe={handleTranscribe}
                            onRun={handleRun}
                            isProcessing={isProcessing}
                          />

                          {processingLogs.length > 0 && <ProcessingLog logs={processingLogs} />}

                          <FormalizationOutput
                            formalization={selectedFormalization || formalizations[0]}
                            onHighlightSegments={setHighlightedSegments}
                            onDownloadMarkdown={handleDownloadMarkdown}
                            onDownloadText={handleDownloadText}
                            onDownloadPdf={handleDownloadPdf}
                            onPrintPdf={handlePrintPdf}
                            onRenameRun={handleRenameFormalization}
                            onDeleteRun={handleDeleteRun}
                          />
                        </div>
                      </div>
                    </TabsContent>

                    <TabsContent value="chat" className="mt-6">
                      <ChatInterface
                        session={selectedSession}
                        onUploadAttachments={handleChatUploadAttachments}
                        onSendMessage={handleChatMessage}
                        isProcessing={isProcessing}
                        className="h-[600px]"
                      />
                    </TabsContent>

                    <TabsContent value="formalizations" className="mt-6">
                      <div className="grid gap-4">
                        {formalizations.length === 0 ? (
                          <div className="text-center py-12 text-slate-500">
                            No formalizations yet. Run one from the Session tab.
                          </div>
                        ) : (
                          formalizations.map((formalization) => (
                            <FormalizationOutput
                              key={formalization.id}
                              formalization={formalization}
                              onHighlightSegments={setHighlightedSegments}
                              onDownloadMarkdown={handleDownloadMarkdown}
                              onDownloadText={handleDownloadText}
                              onDownloadPdf={handleDownloadPdf}
                              onPrintPdf={handlePrintPdf}
                              onRenameRun={handleRenameFormalization}
                              onDeleteRun={handleDeleteRun}
                            />
                          ))
                        )}
                      </div>
                    </TabsContent>
                  </Tabs>
                </motion.div>
              </AnimatePresence>
            )}
          </div>
        </div>
      </main>

      <Dialog open={exportModalOpen} onOpenChange={setExportModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Export Session Bundle</DialogTitle>
            <DialogDescription>Choose export type and artifact formats.</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">Export Type</label>
              <Select value={exportType} onValueChange={setExportType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select export type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full_bundle">full_bundle</SelectItem>
                  <SelectItem value="transcript_only">transcript_only</SelectItem>
                  <SelectItem value="formalization_only">formalization_only</SelectItem>
                  <SelectItem value="dev_bundle">dev_bundle</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">Transcript Formats</label>
              <div className={`space-y-2 ${transcriptFormatsEnabled ? '' : 'opacity-50'}`}>
                {['txt', 'md', 'pdf'].map((fmt) => (
                  <label key={fmt} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={transcriptFormats.includes(fmt)}
                      disabled={!transcriptFormatsEnabled}
                      onCheckedChange={(checked) => toggleTranscriptFormat(fmt, Boolean(checked))}
                    />
                    {fmt}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">Formalization Formats</label>
              <div className={`space-y-2 ${formalizationFormatsEnabled ? '' : 'opacity-50'}`}>
                {['md', 'pdf'].map((fmt) => (
                  <label key={fmt} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={formalizationFormats.includes(fmt)}
                      disabled={!formalizationFormatsEnabled}
                      onCheckedChange={(checked) => toggleFormalizationFormat(fmt, Boolean(checked))}
                    />
                    {fmt}
                  </label>
                ))}
              </div>
            </div>

            {exportType === 'dev_bundle' && (
              <p className="text-xs text-slate-500">
                DEV bundle includes user-facing artifacts plus `dev/` receipts and raw JSON outputs.
              </p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setExportModalOpen(false)} disabled={isExporting}>
              Cancel
            </Button>
            <Button onClick={handleExportZip} disabled={isExporting}>
              {isExporting ? 'Exporting...' : 'Export'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
