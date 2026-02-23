import React, { useState, useRef, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Send, Loader2, Bot, User, Sparkles, Paperclip, X } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import { cn } from "@/lib/utils";

export default function ChatInterface({ 
  session,
  onSendMessage,
  onUploadAttachments,
  isProcessing,
  className 
}) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hello! I'm Stuart, your meeting intelligence assistant. ${
        session?.transcript_json?.length > 0 
          ? "I see you have a transcript loaded. You can ask me questions about it, or run a formalization to extract structured insights."
          : "Upload an audio file to get started, then I'll help you extract insights from your meetings."
      }`
    }
  ]);
  const [input, setInput] = useState('');
  const [scope, setScope] = useState('session');
  const [attachments, setAttachments] = useState([]);
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isProcessing) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');

    // Let parent handle the actual processing
    onSendMessage?.(input, { scope, attachments }, (response) => {
      setMessages(prev => [...prev, { role: 'assistant', content: response }]);
    });
    setAttachments([]);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAttachClick = () => {
    fileRef.current?.click();
  };

  const handleAttachmentFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length || !session?.id) return;
    setIsUploadingAttachments(true);
    try {
      const uploaded = await onUploadAttachments?.(files);
      if (Array.isArray(uploaded) && uploaded.length > 0) {
        setAttachments(uploaded);
      }
    } finally {
      setIsUploadingAttachments(false);
    }
  };

  return (
    <Card className={cn("border-slate-200 flex flex-col", className)}>
      <div className="p-4 border-b border-slate-100 flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
          <Sparkles className="h-5 w-5 text-white" />
        </div>
        <div>
          <h2 className="font-semibold text-slate-800">Stuart</h2>
          <p className="text-xs text-slate-500">Voice Intelligence Assistant</p>
        </div>
        {session?.status && (
          <Badge variant="outline" className="ml-auto capitalize">
            {session.status}
          </Badge>
        )}
      </div>

      <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between gap-3">
        <div className="inline-flex rounded-md border border-slate-200 overflow-hidden">
          <button
            type="button"
            className={cn(
              "px-3 py-1.5 text-xs font-medium",
              scope === 'session' ? "bg-slate-800 text-white" : "bg-white text-slate-600"
            )}
            onClick={() => setScope('session')}
          >
            Session
          </button>
          <button
            type="button"
            className={cn(
              "px-3 py-1.5 text-xs font-medium border-l border-slate-200",
              scope === 'global' ? "bg-slate-800 text-white" : "bg-white text-slate-600"
            )}
            onClick={() => setScope('global')}
          >
            Global (Not Implemented)
          </button>
        </div>
        <div className="text-xs text-slate-500">
          Scope: <span className="font-medium uppercase">{scope}</span>
        </div>
      </div>
      {scope === 'global' && (
        <div className="px-4 py-2 border-b border-amber-200 bg-amber-50 text-xs text-amber-700">
          Global chat is scaffold-only in this runtime. Session scope is the production path.
        </div>
      )}

      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="space-y-4">
          {messages.map((msg, idx) => (
            <div 
              key={idx}
              className={cn(
                "flex gap-3",
                msg.role === 'user' ? "justify-end" : "justify-start"
              )}
            >
              {msg.role === 'assistant' && (
                <div className="h-8 w-8 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                  <Bot className="h-4 w-4 text-slate-600" />
                </div>
              )}
              <div 
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-3",
                  msg.role === 'user' 
                    ? "bg-slate-800 text-white" 
                    : "bg-slate-100 text-slate-700"
                )}
              >
                {msg.role === 'assistant' ? (
                  <div className="prose prose-sm prose-slate max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-sm">{msg.content}</p>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="h-8 w-8 rounded-lg bg-slate-800 flex items-center justify-center flex-shrink-0">
                  <User className="h-4 w-4 text-white" />
                </div>
              )}
            </div>
          ))}
          {isProcessing && (
            <div className="flex gap-3 justify-start">
              <div className="h-8 w-8 rounded-lg bg-slate-100 flex items-center justify-center">
                <Bot className="h-4 w-4 text-slate-600" />
              </div>
              <div className="bg-slate-100 rounded-2xl px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-slate-100">
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          multiple
          onChange={(e) => {
            handleAttachmentFiles(e.target.files);
            e.target.value = '';
          }}
        />
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachments.map((a, idx) => (
              <Badge key={`${a.filename}-${idx}`} variant="secondary" className="text-xs">
                {a.filename}
                <button
                  type="button"
                  className="ml-1 text-slate-500 hover:text-slate-700"
                  onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== idx))}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-[44px] px-3"
            onClick={handleAttachClick}
            disabled={isProcessing || isUploadingAttachments || !session?.id}
            title={session?.id ? "Attach file to this session" : "Select a session first"}
          >
            {isUploadingAttachments ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
          </Button>
          <Textarea
            ref={textareaRef}
            placeholder="Ask about your transcript..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="min-h-[44px] max-h-[120px] resize-none"
            rows={1}
            disabled={isProcessing}
          />
          <Button 
            onClick={handleSend}
            disabled={!input.trim() || isProcessing}
            className="h-[44px] px-4"
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="text-xs text-slate-400 mt-2 text-center">
          Press Enter to send • Shift+Enter for new line • Attachments upload to current session
        </p>
      </div>
    </Card>
  );
}
