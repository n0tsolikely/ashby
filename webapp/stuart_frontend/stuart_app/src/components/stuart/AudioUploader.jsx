import React, { useState, useRef } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Upload, FileAudio, X, Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { stuartClient } from "@/api/stuartClient";

const SUPPORTED_FORMATS = ['.mp3', '.wav', '.m4a', '.ogg', '.webm', '.flac'];

export default function AudioUploader({ onUploadComplete, uploadOptions, disabled, className }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadState, setUploadState] = useState('idle'); // idle, uploading, success, error
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileName, setFileName] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const validateFile = (file) => {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!SUPPORTED_FORMATS.includes(ext)) {
      return `Unsupported format. Please use: ${SUPPORTED_FORMATS.join(', ')}`;
    }
    if (file.size > 500 * 1024 * 1024) { // 500MB limit
      return 'File too large. Maximum size is 500MB.';
    }
    return null;
  };

  const getLocalAudioDurationSeconds = async (file) => {
    const objectUrl = URL.createObjectURL(file);
    try {
      const duration = await new Promise((resolve, reject) => {
        const audio = new Audio();
        const timeout = setTimeout(() => reject(new Error('duration_timeout')), 4000);
        audio.addEventListener('loadedmetadata', () => {
          clearTimeout(timeout);
          resolve(Number.isFinite(audio.duration) ? audio.duration : null);
        });
        audio.addEventListener('error', () => {
          clearTimeout(timeout);
          reject(new Error('duration_error'));
        });
        audio.src = objectUrl;
      });
      return duration;
    } catch {
      return null;
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  };

  const handleFile = async (file) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setUploadState('error');
      return;
    }

    setFileName(file.name);
    setUploadState('uploading');
    setError(null);
    setUploadProgress(0);

    // Simulate progress for UX
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => Math.min(prev + 10, 90));
    }, 200);

    try {
      const uploadResult = await stuartClient.upload(file, uploadOptions || {});
      const durationSeconds =
        (await getLocalAudioDurationSeconds(file)) ||
        Math.round((file.size / (1024 * 1024)) * 60) ||
        null;
      await onUploadComplete?.({
        uploadResult,
        filename: file.name,
        duration_seconds: durationSeconds,
      });
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      setUploadState('success');
    } catch (err) {
      clearInterval(progressInterval);
      setError(err?.message || 'Upload failed. Please try again.');
      setUploadState('error');
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const reset = () => {
    setUploadState('idle');
    setUploadProgress(0);
    setFileName(null);
    setError(null);
  };

  return (
    <Card className={cn("border-slate-200", className)}>
      <CardContent className="p-6">
        {uploadState === 'idle' && (
          <div
            className={cn(
              "border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer",
              isDragging 
                ? "border-slate-400 bg-slate-50" 
                : "border-slate-200 hover:border-slate-300",
              disabled && "opacity-50 cursor-not-allowed"
            )}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => !disabled && inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept={SUPPORTED_FORMATS.join(',')}
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              disabled={disabled}
            />
            <Upload className="h-10 w-10 text-slate-400 mx-auto mb-4" />
            <p className="text-slate-600 font-medium">
              Drop your audio file here
            </p>
            <p className="text-sm text-slate-400 mt-1">
              or click to browse
            </p>
            <p className="text-xs text-slate-400 mt-3">
              Supported: {SUPPORTED_FORMATS.join(', ')} • Max 500MB
            </p>
          </div>
        )}

        {uploadState === 'uploading' && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <FileAudio className="h-8 w-8 text-slate-400" />
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700 truncate">
                  {fileName}
                </p>
                <p className="text-xs text-slate-400">Uploading...</p>
              </div>
            </div>
            <Progress value={uploadProgress} className="h-2" />
          </div>
        )}

        {uploadState === 'success' && (
          <div className="flex items-center justify-between p-4 bg-green-50 rounded-xl">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center">
                <Check className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-green-800 truncate max-w-[200px]">
                  {fileName}
                </p>
                <p className="text-xs text-green-600">Ready for processing</p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={reset}
              className="text-green-600 hover:text-green-700 hover:bg-green-100"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        )}

        {uploadState === 'error' && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-4 bg-red-50 rounded-xl">
              <AlertCircle className="h-5 w-5 text-red-500" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
            <Button variant="outline" onClick={reset} className="w-full">
              Try Again
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
