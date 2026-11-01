/**
 * pages/Intelligence/Intelligence.test.js
 *
 * Render and unit smoke tests for AI Intelligence UI components.
 * Tests components with valid API-shaped payloads, empty states,
 * four-pillar explainability, and edge cases.
 * Runs with `npm test`.
 */

import React from 'react';
import { renderToString } from 'react-dom/server';

import FourPillarCard from './components/FourPillarCard';
import ExecutiveSummaryPanel from './components/ExecutiveSummaryPanel';
import ProjectRisksPanel from './components/ProjectRisksPanel';
import SprintDelaysPanel from './components/SprintDelaysPanel';
import WorkloadBottlenecksPanel from './components/WorkloadBottlenecksPanel';
import OperationsInsightsPanel from './components/OperationsInsightsPanel';

describe('FourPillarCard Component', () => {
  const sampleRec = {
    id: 'rec-test-1',
    category: 'project',
    title: 'Milestone Velocity Drift in Project Alpha',
    observation: 'Completion velocity dropped by 32% over the last two iterations.',
    why_it_matters: 'Key release target will slip by 14 days without mitigation.',
    potential_consequence: 'Client SLA penalties and downstream team blocking.',
    recommended_preventive_action: 'Reallocate 2 senior engineers from lower-priority backlogs.',
    urgency: 'high',
    requires_human_approval: true,
  };

  it('renders all 4 pillars and advisory notices', () => {
    const html = renderToString(<FourPillarCard item={sampleRec} />);

    expect(html).toContain('Milestone Velocity Drift in Project Alpha');
    expect(html).toContain('Observation');
    expect(html).toContain('Why This Matters');
    expect(html).toContain('Possible Future Consequence');
    expect(html).toContain('Recommended Preventive Action');
    expect(html).toContain('Advisory recommendation only');
    expect(html).toContain('High Urgency');
  });

  it('handles null item without crashing', () => {
    const html = renderToString(<FourPillarCard item={null} />);
    expect(html).toBe('');
  });
});

describe('ExecutiveSummaryPanel Component', () => {
  const sampleData = {
    overall_status: 'attention_required',
    executive_brief: 'Enterprise delivery is stable overall with minor delivery risks in sprint planning.',
    recommendations: [
      {
        id: 'rec-1',
        category: 'operations',
        title: 'Support Escalation Review',
        observation: 'Escalations increased this week.',
        why_it_matters: 'Impacts SLA metrics.',
        potential_consequence: 'Customer dissatisfaction.',
        recommended_preventive_action: 'Update tier 1 troubleshooting guides.',
        urgency: 'medium',
      },
    ],
    metadata: {
      model_provider: 'gemini',
      model_name: 'gemini-flash-lite-latest',
      generated_at: '2026-10-31T20:00:00Z',
      is_cached: true,
      is_fallback: false,
    },
  };

  it('renders health status, brief statement, and recommendations', () => {
    const html = renderToString(<ExecutiveSummaryPanel data={sampleData} />);

    expect(html).toContain('Attention Required');
    expect(html).toContain('Enterprise delivery is stable overall');
    expect(html).toContain('Support Escalation Review');
    expect(html).toContain('Cached Result');
    expect(html).toContain('gemini-flash-lite-latest');
  });

  it('renders empty card when data is null', () => {
    const html = renderToString(<ExecutiveSummaryPanel data={null} />);
    expect(html).toContain('No executive summary data available');
  });
});

describe('ProjectRisksPanel Component', () => {
  const sampleData = {
    projects: [
      {
        project_id: 101,
        project_name: 'Autonomous Portal',
        deterministic_risk_level: 'high',
        deterministic_risk_score: 78.5,
        primary_risk_factors: ['Sprint velocity lag', 'Overdue critical tasks'],
        risk_explanation: 'Analysis confirms 5 overdue tasks blocking sprint closure.',
        potential_consequences: 'Deployment date pushed back.',
        recommended_actions: ['Conduct emergency backlog triage', 'Rebalance unassigned items'],
      },
      {
        project_id: 102,
        project_name: 'Billing Integration',
        deterministic_risk_level: 'low',
        deterministic_risk_score: 12.0,
        primary_risk_factors: [],
        risk_explanation: 'All deliverables progressing smoothly ahead of deadline.',
        potential_consequences: '',
        recommended_actions: ['Maintain current sprint pacing'],
      },
    ],
  };

  it('renders deterministic scores, risk badges, and recommendations', () => {
    const html = renderToString(<ProjectRisksPanel data={sampleData} />);

    expect(html).toContain('Autonomous Portal');
    expect(html).toContain('HIGH RISK');
    expect(html).toContain('79'); // Math.round(78.5)
    expect(html).toContain('Sprint velocity lag');
    expect(html).toContain('Conduct emergency backlog triage');

    expect(html).toContain('Billing Integration');
    expect(html).toContain('LOW RISK');
    expect(html).toContain('12');
  });

  it('renders empty state when projects array is empty', () => {
    const html = renderToString(<ProjectRisksPanel data={{ projects: [] }} />);
    expect(html).toContain('No project risk assessments found');
  });
});

describe('SprintDelaysPanel Component', () => {
  const sampleData = {
    sprints: [
      {
        sprint_id: 201,
        sprint_name: 'Sprint 14: Core Auth',
        project_name: 'Autonomous Portal',
        delay_status: 'delayed',
        delay_explanation: 'Sprint duration elapsed at 85% with only 40% task completion.',
        contributing_factors: ['2 blocked items on third-party webhook'],
        recommended_mitigations: ['Split blocked tasks into separate issue'],
      },
      {
        sprint_id: 202,
        sprint_name: 'Sprint 1: Bootstrap',
        project_name: 'New AI Project',
        delay_status: 'insufficient_data',
        delay_explanation: 'Sprint recently initialized; insufficient data for delivery projection.',
        contributing_factors: [],
        recommended_mitigations: ['Check back after first iteration cycle.'],
      },
    ],
  };

  it('renders delay classifications including INSUFFICIENT_DATA and DELAYED', () => {
    const html = renderToString(<SprintDelaysPanel data={sampleData} />);

    expect(html).toContain('Sprint 14: Core Auth');
    expect(html).toContain('DELAYED');
    expect(html).toContain('2 blocked items on third-party webhook');

    expect(html).toContain('Sprint 1: Bootstrap');
    expect(html).toContain('INSUFFICIENT DATA');
    expect(html).toContain('insufficient data for delivery projection');
  });

  it('renders empty state when no sprints', () => {
    const html = renderToString(<SprintDelaysPanel data={{ sprints: [] }} />);
    expect(html).toContain('No active or recent sprints found');
  });
});

describe('WorkloadBottlenecksPanel Component', () => {
  const sampleData = {
    bottlenecks: [
      {
        team_or_project: 'Autonomous Portal Core Team',
        bottleneck_severity: 'high',
        observation: '3 senior backend developers hold 78% of active sprint story points.',
        affected_roles: ['Backend Engineers', 'Tech Leads'],
        suggested_balancing_action: 'Distribute mid-complexity tickets to associate engineers.',
      },
    ],
  };

  it('renders workload distribution, severity, and anonymized roles', () => {
    const html = renderToString(<WorkloadBottlenecksPanel data={sampleData} />);

    expect(html).toContain('Autonomous Portal Core Team');
    expect(html).toContain('High Severity');
    expect(html).toContain('Backend Engineers');
    expect(html).toContain('Tech Leads');
    expect(html).toContain('Distribute mid-complexity tickets');
    expect(html).toContain('Advisory suggestion only');
  });

  it('renders empty state when bottlenecks list is empty', () => {
    const html = renderToString(<WorkloadBottlenecksPanel data={{ bottlenecks: [] }} />);
    expect(html).toContain('No workload bottlenecks or severe allocation imbalances detected');
  });
});

describe('OperationsInsightsPanel Component', () => {
  const sampleData = {
    support_insights: ['Billing renewal issues account for 41% of open tickets.'],
    incident_insights: ['Database connection pool saturation during peak hours.'],
    operational_summary: 'Overall operations require synchronization between billing infrastructure and support workflows.',
    metadata: {
      model_provider: 'gemini',
      model_name: 'gemini-flash-lite-latest',
      generated_at: '2026-10-31T20:00:00Z',
      is_cached: false,
      is_fallback: true,
    },
  };

  it('renders customer support and incident insights with operational summary', () => {
    const html = renderToString(<OperationsInsightsPanel data={sampleData} />);

    expect(html).toContain('Billing renewal issues account for 41% of open tickets.');
    expect(html).toContain('Database connection pool saturation during peak hours.');
    expect(html).toContain('Rule Engine Fallback');
    expect(html).toContain('Overall operations require synchronization');
  });

  it('renders empty card when data is null', () => {
    const html = renderToString(<OperationsInsightsPanel data={null} />);
    expect(html).toContain('No operational insights available');
  });
});
