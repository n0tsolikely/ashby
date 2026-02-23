import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Search, 
  Clock, 
  FileText, 
  User, 
  ChevronRight,
  Loader2,
  X
} from "lucide-react";
import { format } from 'date-fns';
import { cn } from "@/lib/utils";

function formatTimestamp(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function highlightMatch(text, query) {
  if (!query) return text;
  const regex = new RegExp(`(${query})`, 'gi');
  const parts = text.split(regex);
  return parts.map((part, i) => 
    regex.test(part) ? <mark key={i} className="bg-amber-200 rounded px-0.5">{part}</mark> : part
  );
}

export default function SessionSearch({ 
  sessions = [], 
  onSessionSelect,
  onJumpToTimestamp,
  className 
}) {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState('all'); // all, mentioned, spoke
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState([]);

  const performSearch = () => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    setIsSearching(true);
    const searchResults = [];

    sessions.forEach(session => {
      const sessionResults = {
        session,
        matches: [],
        titleMatched: false
      };

      // Parse transcript if needed
      const transcriptJson = typeof session.transcript_json_str === 'string' 
        ? JSON.parse(session.transcript_json_str) 
        : (session.transcript_json || []);
      const speakerMap = typeof session.speaker_map_str === 'string'
        ? JSON.parse(session.speaker_map_str)
        : (session.speaker_map || {});

      // Search in transcript
      if (transcriptJson && transcriptJson.length > 0) {
        transcriptJson.forEach(segment => {
          const matchesContent = segment.text?.toLowerCase().includes(query.toLowerCase());
          const matchesSpeaker = speakerMap[segment.speaker]?.toLowerCase().includes(query.toLowerCase());
          
          if (searchType === 'all' && matchesContent) {
            sessionResults.matches.push({
              type: 'mentioned',
              segment,
              context: segment.text
            });
          } else if (searchType === 'mentioned' && matchesContent) {
            sessionResults.matches.push({
              type: 'mentioned',
              segment,
              context: segment.text
            });
          } else if (searchType === 'spoke' && matchesSpeaker) {
            sessionResults.matches.push({
              type: 'spoke',
              segment,
              speaker: speakerMap[segment.speaker] || segment.speaker,
              context: segment.text
            });
          }
        });
      }

      // Search in formalizations (title, content)
      if (session.title?.toLowerCase().includes(query.toLowerCase())) {
        sessionResults.titleMatched = true;
      }

      if (sessionResults.matches.length > 0 || sessionResults.titleMatched) {
        searchResults.push(sessionResults);
      }
    });

    setResults(searchResults);
    setIsSearching(false);
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
    <Card className={cn("border-slate-200", className)}>
      <CardHeader className="pb-3 border-b border-slate-100">
        <CardTitle className="text-base font-medium text-slate-700">
          Search Sessions
        </CardTitle>
      </CardHeader>

      <CardContent className="p-4 space-y-4">
        {/* Search Input */}
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

        {/* Search Type Filter */}
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
            variant={searchType === 'spoke' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSearchType('spoke')}
          >
            <User className="h-3.5 w-3.5 mr-1.5" />
            Spoke
          </Button>
        </div>

        <Button 
          onClick={performSearch} 
          disabled={!query.trim() || isSearching}
          className="w-full"
        >
          {isSearching ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Search className="h-4 w-4 mr-2" />
          )}
          Search
        </Button>

        {/* Results */}
        {results.length > 0 && (
          <ScrollArea className="h-[400px]">
            <div className="space-y-4">
              {results.map((result, idx) => (
                <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden">
                  {/* Session Header */}
                  <div 
                    className="p-3 bg-slate-50 flex items-center justify-between cursor-pointer hover:bg-slate-100"
                    onClick={() => onSessionSelect?.(result.session)}
                  >
                    <div>
                      <p className="font-medium text-slate-700">
                        {highlightMatch(result.session.title, query)}
                      </p>
                      <p className="text-xs text-slate-500">
                        {format(new Date(result.session.created_date), 'MMM d, yyyy h:mm a')}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-xs">
                        {result.matches.length + (result.titleMatched ? 1 : 0)} matches
                      </Badge>
                      <ChevronRight className="h-4 w-4 text-slate-400" />
                    </div>
                  </div>

                  {/* Matches */}
                  <div className="divide-y divide-slate-100">
                    {result.titleMatched && (
                      <div className="p-3 text-sm text-slate-500">
                        Title match
                      </div>
                    )}
                    {result.matches.slice(0, 5).map((match, mIdx) => (
                      <div 
                        key={mIdx}
                        className="p-3 hover:bg-slate-50 cursor-pointer"
                        onClick={() => {
                          if (match.segment) {
                            onJumpToTimestamp?.(result.session, match.segment.start_time);
                          } else {
                            onSessionSelect?.(result.session);
                          }
                        }}
                      >
                        <div className="flex items-start gap-2">
                          {match.type === 'spoke' && (
                            <Badge variant="outline" className="text-xs flex-shrink-0">
                              <User className="h-3 w-3 mr-1" />
                              {match.speaker}
                            </Badge>
                          )}
                          {match.segment && (
                            <Badge variant="outline" className="text-xs flex-shrink-0">
                              <Clock className="h-3 w-3 mr-1" />
                              {formatTimestamp(match.segment.start_time)}
                            </Badge>
                          )}
                          <p className="text-sm text-slate-600 line-clamp-2">
                            {highlightMatch(match.context, query)}
                          </p>
                        </div>
                      </div>
                    ))}
                    {result.matches.length > 5 && (
                      <div className="p-2 text-center text-xs text-slate-500">
                        +{result.matches.length - 5} more matches
                      </div>
                    )}
                  </div>
                </div>
              ))}
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
