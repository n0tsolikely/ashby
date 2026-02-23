import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Play, Loader2, Shield, Cloud, Wifi, WifiOff, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { MODES, RETENTION_LEVELS, PROFILES, getTemplatesForMode, isValidModeTemplate } from './ModeTemplateConfig';

export default function RunControls({
  session,
  onTranscribe,
  onRun,
  isProcessing,
  className
}) {
  const [mode, setMode] = useState('meeting');
  const [template, setTemplate] = useState('default');
  const [retentionLevel, setRetentionLevel] = useState('MED');
  const [profile, setProfile] = useState(session?.profile || 'LOCAL_ONLY');
  const [diarizationEnabled, setDiarizationEnabled] = useState(session?.diarization_enabled ?? true);
  const [showConfirmation, setShowConfirmation] = useState(false);

  const templates = getTemplatesForMode(mode);
  const hasAudio = (Number(session?.contributions_count || 0) > 0) || Boolean(session?.has_audio);
  const canRun = Boolean(session?.id && hasAudio);

  const handleModeChange = (newMode) => {
    setMode(newMode);
    const newTemplates = getTemplatesForMode(newMode);
    const templateKeys = Object.keys(newTemplates);
    if (templateKeys.length > 0) {
      setTemplate(templateKeys[0]);
    }
  };

  const handleRunClick = () => {
    if (!isValidModeTemplate(mode, template)) {
      return;
    }

    if (profile === 'HYBRID' || profile === 'CLOUD') {
      setShowConfirmation(true);
    } else {
      executeRun();
    }
  };

  const executeRun = () => {
    setShowConfirmation(false);
    onRun?.({
      mode,
      template,
      retention_level: retentionLevel,
      profile,
      diarization_enabled: diarizationEnabled
    });
  };

  const executeTranscribe = () => {
    onTranscribe?.({
      mode: mode === 'journal' ? 'journal' : 'meeting',
      profile,
      diarization_enabled: diarizationEnabled,
      template: 'default',
      retention_level: 'MED',
    });
  };

  const ProfileIcon = profile === 'LOCAL_ONLY' ? WifiOff : profile === 'CLOUD' ? Cloud : Wifi;

  return (
    <>
      <Card className={cn("border-slate-200", className)}>
        <CardHeader className="pb-3 border-b border-slate-100">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-medium text-slate-700">
              Run Configuration
            </CardTitle>
            <Badge className={cn("text-xs", PROFILES[profile]?.color, "text-white")}>
              <ProfileIcon className="h-3 w-3 mr-1" />
              {PROFILES[profile]?.label}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="p-4 space-y-5">
          {/* Mode Selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium text-slate-600">Mode</Label>
            <Select value={mode} onValueChange={handleModeChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(MODES).map(([key, { label, description }]) => (
                  <SelectItem key={key} value={key}>
                    <div>
                      <span className="font-medium">{label}</span>
                      <p className="text-xs text-slate-500">{description}</p>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Template Selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium text-slate-600">Template</Label>
            <Select value={template} onValueChange={setTemplate}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(templates).map(([key, { label }]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Retention Level */}
          <div className="space-y-2">
            <Label className="text-sm font-medium text-slate-600">Retention Level</Label>
            <Select value={retentionLevel} onValueChange={setRetentionLevel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(RETENTION_LEVELS).map(([key, { label, description }]) => (
                  <SelectItem key={key} value={key}>
                    <div>
                      <span className="font-medium">{label}</span>
                      <p className="text-xs text-slate-500">{description}</p>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Profile Selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium text-slate-600">Processing Profile</Label>
            <Select value={profile} onValueChange={setProfile}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PROFILES).map(([key, { label, description }]) => (
                  <SelectItem key={key} value={key} disabled={!PROFILES[key]?.supported}>
                    <div>
                      <span className="font-medium">{label}</span>
                      <p className="text-xs text-slate-500">
                        {!PROFILES[key]?.supported ? `${description} (coming later)` : description}
                      </p>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Diarization Toggle */}
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-slate-500" />
              <div>
                <Label className="text-sm font-medium text-slate-600">Speaker Diarization</Label>
                <p className="text-xs text-slate-400">Identify different speakers</p>
              </div>
            </div>
            <Switch
              checked={diarizationEnabled}
              onCheckedChange={setDiarizationEnabled}
            />
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button
              variant="outline"
              className="h-12 text-base font-medium"
              disabled={!canRun || isProcessing}
              onClick={executeTranscribe}
            >
              {isProcessing ? (
                <>
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                "Transcribe"
              )}
            </Button>
            <Button
              className="h-12 text-base font-medium"
              disabled={!canRun || isProcessing}
              onClick={handleRunClick}
            >
              {isProcessing ? (
                <>
                  <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Play className="h-5 w-5 mr-2" />
                  Run Formalization
                </>
              )}
            </Button>
          </div>

          {!canRun && (
            <p className="text-xs text-center text-slate-400">
              Upload audio before running
            </p>
          )}
        </CardContent>
      </Card>

      {/* Confirmation Dialog for Remote Processing */}
      <AlertDialog open={showConfirmation} onOpenChange={setShowConfirmation}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-amber-500" />
              Confirm Data Processing
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-3">
              <p>
                You've selected <strong>{PROFILES[profile]?.label}</strong> processing mode.
              </p>
              <div className="p-3 bg-amber-50 rounded-lg text-amber-800 text-sm">
                <p className="font-medium">The following data will be sent externally:</p>
                <ul className="list-disc ml-4 mt-2 space-y-1">
                  <li>Transcript text ({session?.transcript_json?.length || 0} segments)</li>
                  <li>Processing configuration</li>
                </ul>
              </div>
              <p className="text-sm">
                This action will be logged. Continue?
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={executeRun}>
              Confirm & Run
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
