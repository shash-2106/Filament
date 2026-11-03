import React from 'react';
import { Outlet } from 'react-router-dom';
import { Navigation } from './Navigation';
import { Header } from './Header';

export const WorkstationShell: React.FC = () => {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-parchment">
      {/* Persistent Left Navigation Sidebar */}
      <Navigation />

      {/* Main Workspace Frame */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Workspace Context Header */}
        <Header />

        {/* Scrollable Content Viewport */}
        <main className="flex-1 overflow-y-auto px-8 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

