import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AssessmentProvider } from './context/AssessmentContext';
import SiteLayout from './components/SiteLayout';
import AssessmentLayout from './components/AssessmentLayout';
import Landing from './pages/Landing';
import Context from './pages/Context';
import Psychometric from './pages/stages/Psychometric';
import AIDiscussion from './pages/stages/AIDiscussion';
import Scenario from './pages/stages/Scenario';
import Processing from './pages/stages/Processing';
import Results from './pages/stages/Results';

function App() {
  return (
    <AssessmentProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<SiteLayout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/context" element={<Context />} />
            <Route element={<AssessmentLayout />}>
              <Route path="/assessment/psychometric" element={<Psychometric />} />
              <Route path="/assessment/ai-discussion" element={<AIDiscussion />} />
              <Route path="/assessment/scenario" element={<Scenario />} />
              <Route path="/assessment/processing" element={<Processing />} />
              <Route path="/assessment/results" element={<Results />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AssessmentProvider>
  );
}

export default App;
