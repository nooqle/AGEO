'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface UseTypewriterOptions {
  text: string;
  speed?: number;
  delay?: number;
  onComplete?: () => void;
}

interface UseTypewriterReturn {
  displayedText: string;
  isTyping: boolean;
  isComplete: boolean;
  skip: () => void;
  reset: () => void;
}

export function useTypewriter({
  text,
  speed = 30,
  delay = 0,
  onComplete,
}: UseTypewriterOptions): UseTypewriterReturn {
  const [state, setState] = useState({
    displayedText: '',
    isTyping: false,
    isComplete: false,
    currentIndex: 0,
    currentText: text,
  });

  const onCompleteRef = useRef(onComplete);

  // Keep onComplete ref up to date
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const skip = useCallback(() => {
    setState(prev => ({
      ...prev,
      displayedText: text,
      isTyping: false,
      isComplete: true,
      currentIndex: text.length,
    }));
    onCompleteRef.current?.();
  }, [text]);

  const reset = useCallback(() => {
    setState(prev => ({
      ...prev,
      displayedText: '',
      isTyping: false,
      isComplete: false,
      currentIndex: 0,
    }));
  }, []);

  // Reset when text changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(prev => {
      if (prev.currentText !== text) {
        return {
          displayedText: '',
          isTyping: false,
          isComplete: false,
          currentIndex: 0,
          currentText: text,
        };
      }
      return prev;
    });
  }, [text]);

  useEffect(() => {
    if (state.isComplete || !text) return;

    const startTyping = setTimeout(() => {
      setState(prev => ({ ...prev, isTyping: true }));
    }, delay);

    return () => clearTimeout(startTyping);
  }, [text, delay, state.isComplete]);

  useEffect(() => {
    if (!state.isTyping || state.isComplete) return;

    if (state.currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setState(prev => ({
          ...prev,
          displayedText: text.slice(0, prev.currentIndex + 1),
          currentIndex: prev.currentIndex + 1,
        }));
      }, speed);

      return () => clearTimeout(timeout);
    } else if (state.currentIndex >= text.length) {
      // Use setTimeout to defer state updates
      const timeout = setTimeout(() => {
        setState(prev => ({
          ...prev,
          isTyping: false,
          isComplete: true,
        }));
        onCompleteRef.current?.();
      }, 0);

      return () => clearTimeout(timeout);
    }
  }, [state.currentIndex, state.isTyping, state.isComplete, text, speed]);

  return {
    displayedText: state.displayedText,
    isTyping: state.isTyping,
    isComplete: state.isComplete,
    skip,
    reset,
  };
}
