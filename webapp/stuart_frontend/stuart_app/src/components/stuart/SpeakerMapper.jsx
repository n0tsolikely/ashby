import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { User, Save, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { speakerIdToDisplayLabel } from "@/lib/speaker_labels";

export default function SpeakerMapper({ 
  transcript = [], 
  speakerIds = [],
  speakerMap = {}, 
  onSpeakerMapUpdate,
  className 
}) {
  const [localMap, setLocalMap] = useState(speakerMap);
  const [hasChanges, setHasChanges] = useState(false);

  // Extract unique speakers from transcript
  const speakers = [...new Set([
    ...speakerIds,
    ...transcript
      .filter(seg => seg.speaker)
      .map(seg => seg.speaker),
  ])].sort();

  // Count segments per speaker
  const speakerCounts = transcript.reduce((acc, seg) => {
    if (seg.speaker) {
      acc[seg.speaker] = (acc[seg.speaker] || 0) + 1;
    }
    return acc;
  }, {});

  // Check for low confidence attributions
  const lowConfidenceSpeakers = transcript
    .filter(seg => seg.speaker && seg.confidence && seg.confidence < 0.7)
    .map(seg => seg.speaker);
  const uncertainSpeakers = [...new Set(lowConfidenceSpeakers)];

  useEffect(() => {
    setLocalMap(speakerMap);
  }, [speakerMap]);

  const handleNameChange = (speakerId, name) => {
    setLocalMap(prev => ({
      ...prev,
      [speakerId]: name
    }));
    setHasChanges(true);
  };

  const handleSave = () => {
    onSpeakerMapUpdate?.(localMap);
    setHasChanges(false);
  };

  if (speakers.length === 0) {
    return null;
  }

  return (
    <Card className={cn("border-slate-200", className)}>
      <CardHeader className="pb-3 border-b border-slate-100">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium text-slate-700">
            Speaker Mapping
          </CardTitle>
          {hasChanges && (
            <Button size="sm" onClick={handleSave}>
              <Save className="h-4 w-4 mr-1.5" />
              Save
            </Button>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1">
          Map speaker labels to actual names (optional)
        </p>
      </CardHeader>

      <CardContent className="p-4 space-y-3">
        {speakers.map(speakerId => {
          const isUncertain = uncertainSpeakers.includes(speakerId);
          return (
            <div 
              key={speakerId}
              className={cn(
                "flex items-center gap-3 p-3 rounded-lg",
                isUncertain ? "bg-amber-50 border border-amber-200" : "bg-slate-50"
              )}
            >
              <div className="h-9 w-9 rounded-full bg-slate-200 flex items-center justify-center">
                <User className="h-4 w-4 text-slate-500" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="text-xs font-mono">
                    {speakerIdToDisplayLabel(speakerId)}
                  </Badge>
                  <span className="text-xs text-slate-400">
                    {speakerCounts[speakerId]} segments
                  </span>
                  {isUncertain && (
                    <Badge variant="secondary" className="text-xs text-amber-700 bg-amber-100">
                      <AlertTriangle className="h-3 w-3 mr-1" />
                      Uncertain
                    </Badge>
                  )}
                </div>
                <Input
                  placeholder="Enter name..."
                  value={localMap[speakerId] || ''}
                  onChange={(e) => handleNameChange(speakerId, e.target.value)}
                  className="h-8 text-sm"
                />
              </div>
            </div>
          );
        })}

        {uncertainSpeakers.length > 0 && (
          <div className="flex items-start gap-2 p-3 bg-amber-50 rounded-lg text-xs text-amber-700">
            <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <p>
              Some speaker attributions have low confidence. 
              Review the transcript carefully before assigning names.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
