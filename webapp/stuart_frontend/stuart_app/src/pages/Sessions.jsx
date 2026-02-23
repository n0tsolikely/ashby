import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Link } from 'react-router-dom';
import { createPageUrl } from '@/utils';
import { format } from 'date-fns';
import { Search, Filter, Calendar, Clock, FileAudio, CheckCircle2, Loader2, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';
import { stuartClient } from '@/api/stuartClient';

const STATUS_CONFIG = {
  needs_upload: { color: 'bg-slate-200 text-slate-700', label: 'Needs Upload' },
  uploaded: { color: 'bg-slate-100 text-slate-600', label: 'Uploaded' },
  processing: { color: 'bg-blue-100 text-blue-700', label: 'Processing' },
  transcribed: { color: 'bg-amber-100 text-amber-700', label: 'Transcribed' },
  formalized: { color: 'bg-green-100 text-green-700', label: 'Formalized' },
  complete: { color: 'bg-green-100 text-green-700', label: 'Complete' },
  failed: { color: 'bg-red-100 text-red-700', label: 'Failed' },
  partial: { color: 'bg-amber-100 text-amber-700', label: 'Partial' },
};

function formatDuration(seconds) {
  if (!seconds) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 60) {
    const hrs = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hrs}h ${remainingMins}m`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function normalizeSession(session) {
  const id = session.id ?? session.session_id;
  const createdTs = session.created_ts;
  const createdDate =
    session.created_date ??
    session.created_at ??
    (typeof createdTs === 'number' ? new Date(createdTs * 1000).toISOString() : new Date().toISOString());
  const contributions = Array.isArray(session.contributions) ? session.contributions : [];
  const contributionsCount = Number(session.contributions_count ?? contributions.length ?? 0);
  const latestStatus = String(session.latest_run?.status || '').toLowerCase();
  const status =
    contributionsCount <= 0
      ? 'needs_upload'
      : ['running', 'queued', 'created'].includes(latestStatus)
        ? 'processing'
        : session.has_formalization
          ? 'complete'
          : session.has_transcript
            ? 'transcribed'
            : 'uploaded';

  return {
    ...session,
    id,
    session_id: session.session_id ?? id,
    created_date: createdDate,
    status,
    contributions,
    contributions_count: contributionsCount,
  };
}

export default function Sessions() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const { data: sessionsRaw = [], isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => stuartClient.sessions.list(),
  });

  const sessions = useMemo(() => sessionsRaw.map(normalizeSession), [sessionsRaw]);

  const stats = {
    total: sessions.length,
    formalized: sessions.filter((s) => s.status === 'formalized').length,
    totalDuration: sessions.reduce((acc, s) => acc + (s.duration_seconds || 0), 0),
  };

  const filteredSessions = sessions.filter((session) => {
    const matchesSearch =
      !searchQuery ||
      session.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      session.audio_filename?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || session.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Session Archive</h1>
            <p className="text-slate-500 mt-1">Browse and search all recorded sessions</p>
          </div>
          <Link to={createPageUrl('Stuart')}>
            <Button>
              New Session
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </Link>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
          <Card className="border-slate-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-slate-100 flex items-center justify-center">
                  <FileAudio className="h-5 w-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-800">{stats.total}</p>
                  <p className="text-xs text-slate-500">Total Sessions</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-green-100 flex items-center justify-center">
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-800">{stats.formalized}</p>
                  <p className="text-xs text-slate-500">Formalized</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-amber-100 flex items-center justify-center">
                  <Clock className="h-5 w-5 text-amber-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-800">{Math.round(stats.totalDuration / 3600)}h</p>
                  <p className="text-xs text-slate-500">Total Duration</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="border-slate-200 mb-6">
          <CardContent className="p-4">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  placeholder="Search sessions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-full sm:w-[180px]">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="uploaded">Uploaded</SelectItem>
                  <SelectItem value="transcribed">Transcribed</SelectItem>
                  <SelectItem value="formalized">Formalized</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <Card className="border-slate-200">
            <CardContent className="py-12 text-center">
              <FileAudio className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-500">No sessions found</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {filteredSessions.map((session, idx) => {
              const statusConfig = STATUS_CONFIG[session.status] || STATUS_CONFIG.uploaded;

              return (
                <motion.div
                  key={session.id || `${session.title}-${idx}`}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.03 }}
                >
                  <Link to={`${createPageUrl('Stuart')}?session=${session.id || ''}`}>
                    <Card className="border-slate-200 hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 mb-1">
                              <h3 className="font-medium text-slate-800 truncate">{session.title || 'Untitled Session'}</h3>
                              <Badge className={statusConfig.color}>{statusConfig.label}</Badge>
                            </div>
                            <div className="flex items-center gap-4 text-sm text-slate-500">
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3.5 w-3.5" />
                                {format(new Date(session.created_date), 'MMM d, yyyy')}
                              </span>
                              <span className="flex items-center gap-1">
                                <Clock className="h-3.5 w-3.5" />
                                {formatDuration(session.duration_seconds)}
                              </span>
                            </div>
                          </div>
                          <ArrowRight className="h-5 w-5 text-slate-400" />
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
