import React, { useState, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChevronDown, ChevronUp, Search, Clock, User, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

function formatTimestamp(seconds) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const mins = Math.floor(safeSeconds / 60);
  const secs = Math.floor(safeSeconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export default function TranscriptViewer({ 
  transcript = [], 
  speakerMap = {}, 
  highlightedSegments = [],
  onSegmentClick,
  className 
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState(null);
  const scrollRef = useRef(null);

  const filteredTranscript = transcript.filter(seg => 
    seg.text?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (seg.speaker && speakerMap[seg.speaker]?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const getSpeakerName = (speakerId) => {
    return speakerMap[speakerId] || speakerId || "Unknown";
  };

  const copySegment = (segment) => {
    const startSeconds =
      Number.isFinite(segment.start_time)
        ? segment.start_time
        : Number.isFinite(segment.start_ms)
          ? segment.start_ms / 1000
          : 0;
    const text = `[${formatTimestamp(startSeconds)}] ${getSpeakerName(segment.speaker)}: ${segment.text}`;
    navigator.clipboard.writeText(text);
    setCopiedId(segment.segment_id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (!transcript || transcript.length === 0) {
    return (
      <Card className={cn("border-slate-200", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium text-slate-600">Transcript</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-400 italic">No transcript available yet</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn("border-slate-200 overflow-hidden", className)}>
      <CardHeader className="pb-2 border-b border-slate-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base font-medium text-slate-700">Transcript</CardTitle>
            <Badge variant="outline" className="text-xs">
              {transcript.length} segments
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-slate-500 hover:text-slate-700"
          >
            {isExpanded ? (
              <>Collapse <ChevronUp className="ml-1 h-4 w-4" /></>
            ) : (
              <>Expand <ChevronDown className="ml-1 h-4 w-4" /></>
            )}
          </Button>
        </div>
        {isExpanded && (
          <div className="relative mt-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Search transcript..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 text-sm"
            />
          </div>
        )}
      </CardHeader>
      
      {isExpanded && (
        <ScrollArea className="h-[400px]" ref={scrollRef}>
          <CardContent className="p-4 space-y-1">
            {filteredTranscript.map((segment, idx) => {
              const isHighlighted = highlightedSegments.includes(segment.segment_id);
              const startSeconds =
                Number.isFinite(segment.start_time)
                  ? segment.start_time
                  : Number.isFinite(segment.start_ms)
                    ? segment.start_ms / 1000
                    : 0;
              return (
                <div
                  key={segment.segment_id || idx}
                  className={cn(
                    "group p-3 rounded-lg transition-all cursor-pointer",
                    isHighlighted 
                      ? "bg-amber-50 border border-amber-200" 
                      : "hover:bg-slate-50"
                  )}
                  onClick={() => onSegmentClick?.(segment)}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex flex-col items-center gap-1 min-w-[60px]">
                      <span className="text-xs font-mono text-slate-400 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTimestamp(startSeconds)}
                      </span>
                      {segment.speaker && (
                        <Badge variant="secondary" className="text-xs px-1.5 py-0">
                          <User className="h-3 w-3 mr-1" />
                          {getSpeakerName(segment.speaker)}
                        </Badge>
                      )}
                    </div>
                    <p className="flex-1 text-sm text-slate-700 leading-relaxed">
                      {segment.text}
                    </p>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        copySegment(segment);
                      }}
                    >
                      {copiedId === segment.segment_id ? (
                        <Check className="h-3.5 w-3.5 text-green-500" />
                      ) : (
                        <Copy className="h-3.5 w-3.5 text-slate-400" />
                      )}
                    </Button>
                  </div>
                  {segment.confidence && segment.confidence < 0.8 && (
                    <p className="mt-1 ml-[72px] text-xs text-amber-600">
                      Low confidence ({Math.round(segment.confidence * 100)}%)
                    </p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </ScrollArea>
      )}
      
      {!isExpanded && (
        <CardContent className="pt-3 pb-4">
          <p className="text-sm text-slate-500 line-clamp-2">
            {transcript[0]?.text}...
          </p>
        </CardContent>
      )}
    </Card>
  );
}
