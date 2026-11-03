import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/auth';
import { WorkstationShell } from './components/layout/WorkstationShell';
import { OverviewPage } from './pages/OverviewPage';
import { MemoryPage } from './pages/MemoryPage';
import { EvidencePage } from './pages/EvidencePage';
import { DependenciesPage } from './pages/DependenciesPage';
import { AgentsPage } from './pages/AgentsPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { ActivityPage } from './pages/ActivityPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30 seconds
      refetchOnWindowFocus: false,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<WorkstationShell />}>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/memory" element={<MemoryPage />} />
              <Route path="/evidence" element={<EvidencePage />} />
              <Route path="/dependencies" element={<DependenciesPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/integrations" element={<IntegrationsPage />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
};

