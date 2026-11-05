import React from 'react';
import { Outlet } from 'react-router-dom';
import { Navigation } from './Navigation';
import { Header } from './Header';

export const WorkstationShell: React.FC = () => {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-graphite text-graphite-text">
      {/* Persistent Left Navigation Sidebar */}
      <Navigation />

      {/* Main Workspace Frame */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative bg-graphite">
        {/* Workspace Context Header with Glass effect */}
        <Header />

        {/* Scrollable Content Viewport */}
        <main className="flex-1 overflow-y-auto px-6 py-5 relative bg-[#0B1210]">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
