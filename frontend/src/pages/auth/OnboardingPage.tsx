import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';

export const OnboardingPage: React.FC = () => {
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('');
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Save onboarding details and redirect to dashboard
    navigate('/');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Tell us about your business
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            This helps us tailor CashIQ to your needs.
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="rounded-md shadow-sm space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
              <Input
                type="text"
                required
                placeholder="Acme Corp"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Industry</label>
              <select 
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                required
              >
                <option value="">Select industry</option>
                <option value="tech">Technology</option>
                <option value="retail">Retail</option>
                <option value="services">Services</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          <div>
            <Button type="submit" className="w-full">
              Complete Setup
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
