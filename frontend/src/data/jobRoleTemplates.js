/**
 * data/jobRoleTemplates.js
 *
 * Pre-built job-role presets for the HR Recruitment posting form.
 * Purely a frontend convenience — picking one just pre-fills the same
 * fields HR would otherwise type from scratch (matches JobPostingCreate
 * exactly: title, requiredSkills, description, experienceLevel,
 * minEducation). No backend involvement.
 */

const JOB_ROLE_TEMPLATES = [
  {
    title: 'Software Engineer',
    requiredSkills: 'JavaScript, React, Node.js, REST APIs, Git',
    description: 'Design, build, and maintain features across our web application stack, working closely with product and design.',
    experienceLevel: 'mid',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'Senior Backend Engineer',
    requiredSkills: 'Python, FastAPI, PostgreSQL, Docker, System Design',
    description: 'Own backend services end to end — API design, data modeling, performance, and reliability — and mentor junior engineers.',
    experienceLevel: 'senior',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'Product Manager',
    requiredSkills: 'Roadmapping, User Research, Analytics, Stakeholder Communication',
    description: 'Define product strategy and roadmap, gather requirements from stakeholders, and work with engineering/design to ship features.',
    experienceLevel: 'mid',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'Data Analyst',
    requiredSkills: 'SQL, Python, Excel, Data Visualization, Statistics',
    description: 'Analyze business data to surface insights, build dashboards, and support data-driven decision making across teams.',
    experienceLevel: 'junior',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'UI/UX Designer',
    requiredSkills: 'Figma, Wireframing, User Research, Prototyping, Design Systems',
    description: 'Design intuitive, accessible user experiences from research through high-fidelity prototypes, collaborating closely with engineering.',
    experienceLevel: 'mid',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'DevOps Engineer',
    requiredSkills: 'AWS/Azure, Docker, Kubernetes, CI/CD, Terraform',
    description: 'Build and maintain deployment pipelines and cloud infrastructure, improving reliability, scalability, and developer velocity.',
    experienceLevel: 'mid',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'QA Engineer',
    requiredSkills: 'Test Automation, Selenium/Playwright, API Testing, Bug Tracking',
    description: 'Design and execute manual and automated test plans to ensure product quality before release.',
    experienceLevel: 'entry',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'HR Executive',
    requiredSkills: 'Recruitment, Onboarding, Employee Relations, HRIS',
    description: 'Manage end-to-end recruitment and onboarding, and support employee relations and HR operations.',
    experienceLevel: 'entry',
    minEducation: "Bachelor's Degree",
  },
  {
    title: 'Sales Executive',
    requiredSkills: 'B2B Sales, CRM, Negotiation, Lead Generation',
    description: 'Drive new business by identifying leads, running the sales cycle, and building long-term client relationships.',
    experienceLevel: 'entry',
    minEducation: "Bachelor's Degree",
  },
];

export default JOB_ROLE_TEMPLATES;
