"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useIsMobile } from "@/hooks/use-media-query";
import { Button } from "@/components/ui/button";
import { RiMenuLine, RiCloseLine, RiAddLine } from "@remixicon/react";

interface ResponsiveChatLayoutProps {
  sidebar: React.ReactNode;
  mainContent: React.ReactNode;
  inputArea: React.ReactNode;
  header?: React.ReactNode;
}

export function ResponsiveChatLayout({
  sidebar,
  mainContent,
  inputArea,
  header,
}: ResponsiveChatLayoutProps) {
  const isMobile = useIsMobile();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);

  return (
    <div className="h-screen flex overflow-hidden bg-[var(--bg-primary)]">
      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{
          x: isMobile ? (isSidebarOpen ? 0 : "-100%") : 0,
          width: isMobile ? (isSidebarOpen ? 280 : 0) : 280,
        }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className={`fixed lg:relative z-50 h-full bg-[var(--bg-secondary)] border-r border-[var(--border-subtle)] overflow-hidden ${
          isMobile ? "left-0 top-0" : ""
        }`}
      >
        <div className="w-[280px] h-full flex flex-col">
          {/* Sidebar Header */}
          <div className="p-4 border-b border-[var(--border-subtle)]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">历史会话</h2>
              {isMobile && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setIsSidebarOpen(false)}
                >
                  <RiCloseLine className="w-5 h-5" />
                </Button>
              )}
            </div>
            <Button className="w-full mt-3" leftIcon={<RiAddLine className="w-4 h-4" />}>
              新建分析
            </Button>
          </div>

          {/* Sidebar Content */}
          <div className="flex-1 overflow-y-auto">{sidebar}</div>
        </div>
      </motion.aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-14 border-b border-[var(--border-subtle)] flex items-center px-4 bg-[var(--bg-secondary)]">
          {isMobile && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsSidebarOpen(true)}
              className="mr-2"
            >
              <RiMenuLine className="w-5 h-5" />
            </Button>
          )}
          {header || (
            <h1 className="text-lg font-semibold text-[var(--text-primary)]">Specta AI</h1>
          )}
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-hidden relative">
          <div className="absolute inset-0 overflow-y-auto pb-20">{mainContent}</div>
        </div>

        {/* Input Area */}
        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          {inputArea}
        </div>
      </div>
    </div>
  );
}
