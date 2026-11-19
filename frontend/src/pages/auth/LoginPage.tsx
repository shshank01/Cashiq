import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { useAuth } from '../../contexts/AuthContext';
import { authApi } from '../../api/auth';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('demo@cashiq.io');
  const [password, setPassword] = useState('password123');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const res = await authApi.login({ email, password });
      login(res.access_token, res.user);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid email or password. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#FBFBFA] py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl border border-stone-200 shadow-sm">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto rounded-xl bg-teal-600 flex items-center justify-center text-white font-serif font-bold text-2xl shadow-sm mb-4">
            Q
          </div>
          <h2 className="text-2xl font-serif font-bold text-stone-900 tracking-tight">
            Sign in to Cash<span className="text-teal-700">IQ</span>
          </h2>
          <p className="text-xs text-stone-500 mt-1">
            AI-powered financial intelligence for growing businesses
          </p>
        </div>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
            {error}
          </div>
        )}

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Work Email</label>
            <Input
              type="email"
              required
              placeholder="demo@cashiq.io"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Password</label>
            <Input
              type="password"
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div className="pt-2">
            <Button type="submit" isLoading={isLoading} className="w-full">
              Sign In to Workspace
            </Button>
          </div>
          
          <div className="text-center text-xs pt-2">
            <span className="text-stone-500">Don't have an account? </span>
            <Link to="/register" className="font-semibold text-teal-700 hover:text-teal-800">
              Create an account
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
