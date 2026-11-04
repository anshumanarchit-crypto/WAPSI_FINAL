import React, { useState } from 'react';
import { useDemoStore, TeamMember } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { 
  Users, 
  X, 
  UserPlus, 
  ShieldCheck, 
  Trash2, 
  Mail, 
  CheckCircle2 
} from 'lucide-react';

export const UserManagementModal: React.FC = () => {
  const isUserManagementModalOpen = useDemoStore((state) => state.isUserManagementModalOpen);
  const setUserManagementModalOpen = useDemoStore((state) => state.setUserManagementModalOpen);
  const teamMembers = useDemoStore((state) => state.teamMembers);
  const addTeamMember = useDemoStore((state) => state.addTeamMember);
  const removeTeamMember = useDemoStore((state) => state.removeTeamMember);

  const [newMemberName, setNewMemberName] = useState('');
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<'Admin' | 'Recovery Ops' | 'Risk Officer' | 'Auditor'>('Recovery Ops');
  const [showAddForm, setShowAddForm] = useState(false);

  if (!isUserManagementModalOpen) return null;

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberName || !newMemberEmail) return;
    addTeamMember({
      name: newMemberName,
      email: newMemberEmail,
      role: newMemberRole,
      status: 'Active',
      lastActive: 'Just now',
    });
    setNewMemberName('');
    setNewMemberEmail('');
    setShowAddForm(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="bg-[#0F172A] border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="p-5 bg-[#0B0F19] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                User Management & Team Access
              </h2>
              <p className="text-xs text-slate-400">Manage operators, permissions, and recovery audit roles</p>
            </div>
          </div>
          <button
            onClick={() => setUserManagementModalOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          <div className="flex items-center justify-between pb-2">
            <span className="font-semibold text-slate-300">
              Active Operators ({teamMembers.length})
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowAddForm(!showAddForm)}
              className="gap-1.5 text-xs"
            >
              <UserPlus className="w-3.5 h-3.5" />
              Invite Team Member
            </Button>
          </div>

          {showAddForm && (
            <form onSubmit={handleAdd} className="p-3.5 rounded-xl bg-slate-950 border border-indigo-500/30 space-y-3 animate-in fade-in">
              <span className="font-bold text-indigo-300 block">Invite New Operator</span>
              <div className="grid grid-cols-3 gap-2.5">
                <Input
                  placeholder="Full Name"
                  value={newMemberName}
                  onChange={(e) => setNewMemberName(e.target.value)}
                  required
                />
                <Input
                  placeholder="name@acmecorp.com"
                  type="email"
                  value={newMemberEmail}
                  onChange={(e) => setNewMemberEmail(e.target.value)}
                  required
                />
                <select
                  value={newMemberRole}
                  onChange={(e) => setNewMemberRole(e.target.value as any)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-2 text-xs text-slate-200"
                >
                  <option value="Admin">Admin</option>
                  <option value="Recovery Ops">Recovery Ops</option>
                  <option value="Risk Officer">Risk Officer</option>
                  <option value="Auditor">Auditor</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="ghost" size="sm" onClick={() => setShowAddForm(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm">
                  Send Invitation
                </Button>
              </div>
            </form>
          )}

          {/* Members Table */}
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/60">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/60 text-slate-400 font-semibold uppercase text-[10px]">
                  <th className="py-2.5 px-3">Name & Email</th>
                  <th className="py-2.5 px-3">Role</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Last Active</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {teamMembers.map((member) => (
                  <tr key={member.id} className="hover:bg-slate-900/40">
                    <td className="py-2.5 px-3">
                      <span className="font-semibold text-white block">{member.name}</span>
                      <span className="text-[10px] text-slate-400 font-mono">{member.email}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                        {member.role}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="text-emerald-400 text-[11px] font-medium flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        {member.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                      {member.lastActive}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {member.id !== 'tm-1' && (
                        <button
                          onClick={() => removeTeamMember(member.id)}
                          className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0B0F19] border-t border-slate-800 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => setUserManagementModalOpen(false)}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};
