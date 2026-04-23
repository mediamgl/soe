import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import SiteLayout from './components/SiteLayout';
import AssessmentLayout from './components/AssessmentLayout';
import Landing from './pages/Landing';
import Start from './pages/Start';
import Context from './pages/Context';
import Psychometric from './pages/stages/Psychometric';
import AIDiscussion from './pages/stages/AIDiscussion';
import Scenario from './pages/stages/Scenario';
import Processing from './pages/stages/Processing';
import Results from './pages/stages/Results';
import AdminLayout from './pages/admin/AdminLayout';
import AdminLogin from './pages/admin/AdminLogin';
import AdminIndex from './pages/admin/AdminIndex';
import AdminSettings from './pages/admin/AdminSettings';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public site */}
        <Route element={<SiteLayout />}>
          <Route path="/" element={<Landing />} />
          <Route path="/start" element={<Start />} />
          <Route path="/context" element={<Context />} />
          <Route element={<AssessmentLayout />}>
            <Route path="/assessment/psychometric" element={<Psychometric />} />
            <Route path="/assessment/ai-discussion" element={<AIDiscussion />} />
            <Route path="/assessment/scenario" element={<Scenario />} />
            <Route path="/assessment/processing" element={<Processing />} />
            <Route path="/assessment/results" element={<Results />} />
          </Route>
        </Route>

        {/* Admin (no SiteLayout / public footer) */}
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminIndex />} />
          <Route path="settings" element={<AdminSettings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
