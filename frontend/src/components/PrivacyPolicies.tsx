import React, { useState } from 'react';

interface AccordionItemProps {
  title: string;
  children: React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
}

const AccordionItem = ({ title, children, isOpen, onToggle }: AccordionItemProps) => (
  <div className="border-b border-gray-200 dark:border-gray-700 last:border-0">
    <button
      onClick={onToggle}
      className="w-full py-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors px-2"
    >
      <span className="font-bold text-gray-900 dark:text-white">{title}</span>
      <svg
        className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>
    {isOpen && (
      <div className="pb-6 px-2 text-sm text-gray-700 dark:text-gray-300 leading-relaxed animate-in slide-in-from-top-2 duration-200">
        {children}
      </div>
    )}
  </div>
);

const PrivacyPolicies = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggle = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <div className="divide-y divide-gray-200 dark:divide-gray-700">
      <AccordionItem
        title="1. Governance & Actors Identification"
        isOpen={openIndex === 0}
        onToggle={() => toggle(0)}
      >
        <p>
          The processing of personal data within the &quot;Chatbot USMS&quot; (AI Assistant Agent) system is strictly governed by 
          the General Data Protection Regulation (GDPR) and relevant national data protection frameworks.
        </p>
        <ul className="list-disc pl-5 mt-3 space-y-2">
          <li><strong>Data Controller:</strong> École Nationale des Sciences Appliquées (ENSA) de Béni Mellal, represented by its institutional management.</li>
          <li><strong>Data Processor:</strong> The system utilizes Groq Cloud and LLM models as sub-processors for generating academic content.</li>
          <li><strong>Legal Basis:</strong> Mission of Public Interest (Article 6(1)(e) of the GDPR), aimed at enhancing academic support and pedagogical innovation.</li>
        </ul>
      </AccordionItem>

      <AccordionItem
        title="2. Usage Policy (Terms of Service)"
        isOpen={openIndex === 1}
        onToggle={() => toggle(1)}
      >
        <p>
          This AI Assistant Agent is provided exclusively for <strong>academic and pedagogical purposes</strong> to the registered students and internal staff of ENSA de Béni Mellal.
        </p>
        <ul className="list-disc pl-5 mt-3 space-y-2">
          <li><strong>Prohibited Content:</strong> Users are strictly prohibited from inputting &quot;Special Categories of Personal Data&quot; (Article 9 GDPR), including health data, political opinions, or private identifiers.</li>
          <li><strong>Human Validation:</strong> AI-generated outputs must be critically evaluated and verified against official course materials and faculty instructions.</li>
          <li><strong>Acceptable Use:</strong> Misuse of the system or intentional introduction of sensitive data may result in suspension of access and administrative review.</li>
        </ul>
      </AccordionItem>

      <AccordionItem
        title="3. Data Privacy & Your Rights"
        isOpen={openIndex === 2}
        onToggle={() => toggle(2)}
      >
        <p>
          We adhere strictly to the principle of <strong>Data Minimization</strong> and <strong>Storage Limitation</strong>.
        </p>
        <ul className="list-disc pl-5 mt-3 space-y-2">
          <li><strong>Data Minimization:</strong> User prompts are truncated before storage. Additionally, a technical masking layer automatically redacts PII (Emails, Phone Numbers) before any data is sent to external processors.</li>
          <li><strong>Storage Limitation:</strong> Conversations are automatically deleted from our production database after 180 days (one academic semester) to ensure we don&apos;t keep data longer than necessary.</li>
          <li><strong>Right to Erasure:</strong> You may exercise your right to delete your entire conversation history or your account at any time through the Profile page.</li>
          <li><strong>Right to Portability:</strong> You can download a machine-readable JSON export of all your interaction data through the &quot;Download My Data&quot; button in your profile.</li>
          <li><strong>Right to Object:</strong> Users have the right to contest any output that appears inaccurate, biased, or inappropriate through the &quot;Report Inaccuracy&quot; mechanism.</li>
          <li><strong>Accountability:</strong> Critical system actions (login, exports, deletions, etc.) are logged (Audit Trail) for security and compliance oversight.</li>
        </ul>
      </AccordionItem>

      <AccordionItem
        title="4. Cookies & Technical Data"
        isOpen={openIndex === 3}
        onToggle={() => toggle(3)}
      >
        <p>
          The system uses local storage and secure sessions to maintain your authentication state and preferences (language, theme). 
          No third-party tracking cookies are used for advertising. Technical logs are kept for a limited duration to ensure system security and stability.
        </p>
      </AccordionItem>
    </div>
  );
};

export default PrivacyPolicies;
