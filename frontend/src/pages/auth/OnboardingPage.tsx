import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { workspacesApi } from '../../api/workspaces';

export const OnboardingPage: React.FC = () => {
  const { currentWorkspace, refreshWorkspaces } = useWorkspace();
  const [companyName, setCompanyName] = useState(currentWorkspace?.name || '');
  const [industry, setIndustry] = useState('Technology');
  const [businessType, setBusinessType] = useState('B2B SaaS');
  const [operatingModel, setOperatingModel] = useState('B2B');
  const [isSaving, setIsSaving] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      if (currentWorkspace) {
        await workspacesApi.onboarding(currentWorkspace.id, {
          company_name: companyName || currentWorkspace.name,
          industry,
          business_type: businessType,
          operating_model: operatingModel,
        });
        await refreshWorkspaces();
      }
      navigate('/');
    } catch (err) {
      console.error('Failed to save onboarding business profile:', err);
      navigate('/');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Tell us about your business
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            This derives your initial expense relevance profile for context-aware anomaly detection.
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
                <option value="Technology">Technology / SaaS</option>
                <option value="Restaurant">Restaurant / Food & Beverage</option>
                <option value="Retail">Retail / E-commerce</option>
                <option value="Consulting">Agency / Consulting</option>
                <option value="Healthcare">Healthcare / Medical</option>
                <option value="Manufacturing">Manufacturing / Logistics</option>
                <option value="Construction">Construction / Real Estate</option>
                <option value="Education">Education / Training</option>
                <option value="Agriculture">Agriculture & Farming</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Business Type</label>
              <Input
                type="text"
                required
                placeholder="e.g. B2B SaaS, Cloud Kitchen, D2C Brand"
                value={businessType}
                onChange={(e) => setBusinessType(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Operating Model</label>
              <select
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                value={operatingModel}
                onChange={(e) => setOperatingModel(e.target.value)}
                required
              >
                <option value="B2B">B2B</option>
                <option value="B2C">B2C</option>
                <option value="D2C">D2C</option>
                <option value="Remote-First">Remote-First</option>
                <option value="Brick-and-Mortar">Brick-and-Mortar</option>
                <option value="Marketplace">Marketplace</option>
                <option value="Hybrid">Hybrid</option>
              </select>
            </div>
          </div>

          <div>
            <Button type="submit" className="w-full" disabled={isSaving}>
              {isSaving ? 'Saving Profile...' : 'Complete Setup'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
