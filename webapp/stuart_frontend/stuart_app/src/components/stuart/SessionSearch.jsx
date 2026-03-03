import React, { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Search, Clock, FileText, User, Hash, ChevronRight, Loader2, X } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { stuartClient } from '@/api/stuartClient';

function formatTimestamp(seconds) {
  const safe = Number(seconds || 0);
  const mins = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function escapeRegExp(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightMatch(text, query) {
  if (!query) return text;
  const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
  const parts = String(text || '').split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? <mark key={i} className="bg-amber-200 rounded px-0.5">{part}</mark> : part,
  );
}

function toSessionDate(session) {
  const raw = session?.created_date || session?.created_at;
  if (raw) return new Date(raw);
  const ts = Number(session?.created_ts || 0);
  if (ts > 0) return new Date(ts * 1000);
  return new Date();
}

function normalizeMentionHit(hit) {
  return {
    type: 'MENTION_MATCH',
    context: String(hit?.snippet || ''),
    t_start: Number(hit?.t_start || 0),
    segment_id: hit?.segment_id ?? null,
  };
}

function sortResults(rows) {
  return [...rows].sort((a, b) => {
    const ad = Number(a?.session?.created_ts || 0);
    const bd = Number(b?.session?.created_ts || 0);
    if (bd !== ad) return bd - ad;
    return String(a?.session?.session_id || '').localeCompare(String(b?.session?.session_id || ''));
  });
}

export default function SessionSearch({
  sessions = [],
  onSessionSelect,
  onJumpToTimestamp,
  className,
}) {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState('all'); // all, mentioned, attendee
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState([]);

  const sessionsById = useMemo(() => {
    const map = new Map();
    for (const s of sessions) {
      const sid = String(s?.session_id || s?.id || '');
      if (sid) map.set(sid, s);
    }
    return map;
  }, [sessions]);

  const performSearch = async () => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }

    setIsSearching(true);
    try {
      if (searchType === 'mentioned') {
        const mentionedHits = await stuartClient.search.mentioned(q, { limit: 100 });
        const grouped = new Map();
        for (const hit of mentionedHits) {
          const sid = String(hit?.session_id || '');
          if (!sid) continue;
          if (!grouped.has(sid)) grouped.set(sid, []);
          grouped.get(sid).push(normalizeMentionHit(hit));
        }

        const out = [];
        for (const [sid, hits] of grouped.entries()) {
          const session = sessionsById.get(sid);
          if (!session) continue;
          out.push({
            session,
            matchKinds: ['MENTION_MATCH'],
            mentions: hits,
          });
        }
        setResults(sortResults(out));
        return;
      }

      if (searchType === 'attendee') {
        const attendeeRows = await stuartClient.sessions.list({ attendee: q });
        const out = attendeeRows.map((row) => {
          const sid = String(row?.session_id || row?.id || '');
          return {
            session: sessionsById.get(sid) || row,
            matchKinds: ['ATTENDEE_MATCH'],
            mentions: [],
          };
        });
        setResults(sortResults(out));
        return;
      }

      // ALL = union(title/id + attendee + mentioned)
      const [qRows, attendeeRows, mentionedHits] = await Promise.all([
        stuartClient.sessions.list({ q }),
        stuartClient.sessions.list({ attendee: q }),
        stuartClient.search.mentioned(q, { limit: 100 }),
      ]);

      const bySid = new Map();

      for (const row of qRows) {
        const sid = String(row?.session_id || row?.id || '');
        if (!sid) continue;
        const kinds = Array.isArray(row?.match_kinds) ? row.match_kinds : ['TITLE_MATCH', 'ID_MATCH'];
        bySid.set(sid, {
          session: sessionsById.get(sid) || row,
          matchKinds: new Set(kinds),
          mentions: [],
        });
      }

      for (const row of attendeeRows) {
        const sid = String(row?.session_id || row?.id || '');
        if (!sid) continue;
        if (!bySid.has(sid)) {
          bySid.set(sid, { session: sessionsById.get(sid) || row, matchKinds: new Set(), mentions: [] });
        }
        bySid.get(sid).matchKinds.add('ATTENDEE_MATCH');
      }

      for (const hit of mentionedHits) {
        const sid = String(hit?.session_id || '');
        if (!sid) continue;
        if (!bySid.has(sid)) {
          const session = sessionsById.get(sid);
          if (!session) continue;
          bySid.set(sid, { session, matchKinds: new Set(), mentions: [] });
        }
        bySid.get(sid).matchKinds.add('MENTION_MATCH');
        bySid.get(sid).mentions.push(normalizeMentionHit(hit));
      }

      const out = [];
      for (const value of bySid.values()) {
        out.push({
          session: value.session,
          matchKinds: Array.from(value.matchKinds).sort(),
          mentions: value.mentions,
        });
      }
      setResults(sortResults(out));
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      performSearch();
    }
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
  };

  return (
    <Card className={cn('border-slate-200', className)}>
      <CardHeader className="pb-3 border-b border-slate-100">
        <CardTitle className="text-base font-medium text-slate-700">Search Sessions</CardTitle>
      </CardHeader>

      <CardContent className="p-4 space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search sessions..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="pl-9 pr-9"
          />
          {query && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
              onClick={clearSearch}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="flex gap-2">
          <Button
            variant={searchType === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSearchType('all')}
          >
            All
          </Button>
          <Button
            variant={searchType === 'mentioned' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSearchType('mentioned')}
          >
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            Mentioned
          </Button>
          <Button
            variant={searchType === 'attendee' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSearchType('attendee')}
          >
            <User className="h-3.5 w-3.5 mr-1.5" />
            Attendee
          </Button>
        </div>

        <Button onClick={performSearch} disabled={!query.trim() || isSearching} className="w-full">
          {isSearching ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Search className="h-4 w-4 mr-2" />
          )}
          Search
        </Button>

        {results.length > 0 && (
          <ScrollArea className="h-[400px]">
            <div className="space-y-4">
              {results.map((result, idx) => {
                const session = result.session || {};
                const matchKinds = Array.isArray(result.matchKinds) ? result.matchKinds : [];
                return (
                  <div key={`${session.session_id || session.id || idx}`} className="border border-slate-200 rounded-lg overflow-hidden">
                    <div
                      className="p-3 bg-slate-50 flex items-center justify-between cursor-pointer hover:bg-slate-100"
                      onClick={() => onSessionSelect?.(session)}
                    >
                      <div>
                        <p className="font-medium text-slate-700">
                          {highlightMatch(session.title || session.session_id, query)}
                        </p>
                        <p className="text-xs text-slate-500">
                          {format(toSessionDate(session), 'MMM d, yyyy h:mm a')}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">
                          {matchKinds.length + (result.mentions?.length || 0)} matches
                        </Badge>
                        <ChevronRight className="h-4 w-4 text-slate-400" />
                      </div>
                    </div>

                    <div className="p-3 border-t border-slate-100 flex flex-wrap gap-2">
                      {matchKinds.includes('TITLE_MATCH') && <Badge variant="outline">Title</Badge>}
                      {matchKinds.includes('ID_MATCH') && (
                        <Badge variant="outline">
                          <Hash className="h-3 w-3 mr-1" />
                          ID
                        </Badge>
                      )}
                      {matchKinds.includes('ATTENDEE_MATCH') && (
                        <Badge variant="outline">
                          <User className="h-3 w-3 mr-1" />
                          Attendee
                        </Badge>
                      )}
                      {matchKinds.includes('MENTION_MATCH') && (
                        <Badge variant="outline">
                          <FileText className="h-3 w-3 mr-1" />
                          Mentioned
                        </Badge>
                      )}
                    </div>

                    {Array.isArray(result.mentions) && result.mentions.length > 0 && (
                      <div className="divide-y divide-slate-100">
                        {result.mentions.slice(0, 5).map((hit, hIdx) => (
                          <div
                            key={`${session.session_id || session.id}_${hIdx}`}
                            className="p-3 hover:bg-slate-50 cursor-pointer"
                            onClick={() => {
                              if (typeof hit.t_start === 'number') {
                                onJumpToTimestamp?.(session, hit.t_start);
                              } else {
                                onSessionSelect?.(session);
                              }
                            }}
                          >
                            <div className="flex items-start gap-2">
                              <Badge variant="outline" className="text-xs flex-shrink-0">
                                <Clock className="h-3 w-3 mr-1" />
                                {formatTimestamp(hit.t_start)}
                              </Badge>
                              <p className="text-sm text-slate-600 line-clamp-2">
                                {highlightMatch(hit.context, query)}
                              </p>
                            </div>
                          </div>
                        ))}
                        {result.mentions.length > 5 && (
                          <div className="p-2 text-center text-xs text-slate-500">
                            +{result.mentions.length - 5} more mentions
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}

        {query && results.length === 0 && !isSearching && (
          <div className="text-center py-8">
            <Search className="h-10 w-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No results found</p>
            <p className="text-sm text-slate-400">Try a different search term</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
